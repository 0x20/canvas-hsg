"""
Spotify Manager

Handles Spotify Connect state tracking and integration with audio playback.
Downloads album art and triggers "Now Playing" display on the physical screen.

Librespot 0.8 onevent flow:
  1. track_changed  — has NAME, ARTISTS, ALBUM, COVERS, DURATION_MS
  2. playing        — has TRACK_ID, POSITION_MS only
  3. paused/stopped — has TRACK_ID only
"""
import asyncio
import logging
import aiohttp
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any


class SpotifyManager:
    """Manages Spotify Connect state and integration"""

    COVER_ART_PATH = "/tmp/stream_images/spotify_cover.jpg"
    STATE_FILE = "/tmp/spotify_state.json"

    def __init__(self, audio_manager=None, background_manager=None, websocket_manager=None):
        self.audio_manager = audio_manager
        self.background_manager = background_manager
        self.websocket_manager = websocket_manager
        self.playback_manager = None
        self.ha_manager = None

        # Current Spotify state
        self.is_playing = False
        self.is_session_connected = False
        self.current_track_id: Optional[str] = None
        self.track_info: Dict[str, Any] = {}
        self.last_event: Optional[str] = None
        self.last_event_time: Optional[datetime] = None

        # Ensure temp dir exists
        Path("/tmp/stream_images").mkdir(exist_ok=True)

    async def initialize(self):
        """Initialize and restore state from disk if available"""
        await self._restore_state()

        # Broadcast initial state to WebSocket clients (React will handle view switching)
        if self.is_playing and self.track_info.get("name"):
            logging.info(f"Restored Spotify state: {self.track_info['name']} by {self.track_info.get('artists')}")
            logging.info(f"Spotify is playing - React will show now-playing view")

            # Broadcast state so React switches to now-playing view
            if self.websocket_manager:
                await self.websocket_manager.broadcast("spotify_state", {
                    "is_playing": True
                })
        else:
            logging.info("Spotify is not playing - React will show static background")

    async def handle_event(self, event: str, track_id: Optional[str] = None,
                          old_track_id: Optional[str] = None,
                          duration_ms: Optional[int] = None,
                          position_ms: Optional[int] = None,
                          name: Optional[str] = None,
                          artists: Optional[str] = None,
                          album: Optional[str] = None,
                          covers: Optional[str] = None) -> bool:
        """Handle Spotify event from librespot onevent hook"""
        try:
            self.last_event = event
            self.last_event_time = datetime.now()

            logging.info(f"Spotify event: {event} (track_id={track_id}, name={name})")

            if event == "session_connected":
                self.is_session_connected = True
                logging.info("Spotify session connected")

            elif event == "track_changed":
                # track_changed carries all metadata: NAME, ARTISTS, ALBUM, COVERS, DURATION_MS
                self.current_track_id = track_id

                self.track_info = {
                    "track_id": track_id,
                    "duration_ms": duration_ms,
                    "started_at": datetime.now().isoformat(),
                }
                if name:
                    self.track_info["name"] = name
                if artists:
                    self.track_info["artists"] = artists
                if album:
                    self.track_info["album"] = album
                if covers:
                    self.track_info["album_art_url"] = covers

                self._store_spotify_url(track_id)

                # ALWAYS broadcast track change via WebSocket (this updates the page)
                if name and self.websocket_manager:
                    cover_url = covers if covers else None
                    # Format artists: replace newlines with comma-space
                    formatted_artists = artists.replace('\n', ', ') if artists else "Unknown Artist"
                    # Build Spotify URL
                    spotify_url = None
                    if track_id:
                        # Handle both spotify:track:ID and bare ID formats
                        if track_id.startswith("spotify:track:"):
                            spotify_id = track_id.split(":")[-1]
                        else:
                            spotify_id = track_id
                        spotify_url = f"https://open.spotify.com/track/{spotify_id}"

                    logging.info(f"Broadcasting track_changed: {name} by {formatted_artists}, album_art_url={cover_url}, spotify_url={spotify_url}")
                    await self.websocket_manager.broadcast("track_changed", {
                        "name": name,
                        "artists": formatted_artists,
                        "album": album or "",
                        "album_art_url": cover_url,
                        "duration_ms": duration_ms,
                        "spotify_url": spotify_url
                    })
                    logging.info("Broadcast complete")

                # View switching is now handled by React via WebSocket
                # Chromium stays running, React switches between StaticBackground and NowPlaying

                logging.info(f"Spotify track changed: {name} - {artists}")

            elif event == "playing":
                was_playing = self.is_playing
                self.is_playing = True

                # Don't update track_id from playing event - it can be stale/wrong
                # track_changed is the authoritative source for track changes
                if track_id and position_ms is not None:
                    self.track_info["position_ms"] = position_ms

                # Stop audio and video playback when Spotify starts playing (only first time)
                if not was_playing:
                    if self.audio_manager:
                        logging.info("Spotify started playing - stopping audio streams")
                        await self.audio_manager.stop_audio_stream()
                    if self.playback_manager:
                        logging.info("Spotify started playing - stopping video playback")
                        await self.playback_manager.stop_playback()

                # Broadcast state change via WebSocket
                if self.websocket_manager:
                    await self.websocket_manager.broadcast("spotify_state", {
                        "is_playing": True
                    })

                logging.info(f"Spotify now playing: {self.track_info.get('name', track_id)}")

            elif event == "paused":
                self.is_playing = False
                logging.info("Spotify playback paused")

                # Broadcast state change via WebSocket (React will switch views)
                if self.websocket_manager:
                    await self.websocket_manager.broadcast("spotify_state", {
                        "is_playing": False
                    })

            elif event in ("stopped", "session_disconnected"):
                self.is_playing = False
                if event == "session_disconnected":
                    self.is_session_connected = False
                self.current_track_id = None
                self.track_info = {}
                logging.info(f"Spotify {event}")

                # Broadcast state change via WebSocket (React will switch views)
                if self.websocket_manager:
                    await self.websocket_manager.broadcast("spotify_state", {
                        "is_playing": False
                    })

            elif event == "volume_changed":
                logging.info("Spotify volume changed")

            else:
                logging.debug(f"Unhandled Spotify event: {event}")

            # Save state after each event
            await self._save_state()

            # Notify Home Assistant of state change
            if self.ha_manager:
                asyncio.create_task(self.ha_manager.notify_state_change())

            return True

        except Exception as e:
            logging.error(f"Failed to handle Spotify event {event}: {e}")
            return False

    async def _update_now_playing_display(self, name: str, artists: Optional[str],
                                          album: Optional[str], covers: Optional[str],
                                          skip_delete: bool = False) -> None:
        """Trigger the web-based now-playing display via Chromium kiosk mode"""
        try:
            # Switch to now-playing view (starts Chromium if needed, or navigates if already running)
            # WebSocket will handle real-time updates of track info to the page
            success = await self.background_manager.switch_to_now_playing()

            if not success:
                logging.error("Failed to switch to now-playing view")

        except Exception as e:
            logging.error(f"Failed to update now-playing display: {e}")

    async def _download_cover_art(self, url: Optional[str]) -> Optional[str]:
        """Download album cover art from URL to local file"""
        if not url:
            return None

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status == 200:
                        data = await resp.read()
                        with open(self.COVER_ART_PATH, "wb") as f:
                            f.write(data)
                        logging.info(f"Downloaded album art ({len(data)} bytes)")
                        return self.COVER_ART_PATH
                    else:
                        logging.warning(f"Failed to download album art: HTTP {resp.status}")
        except Exception as e:
            logging.warning(f"Failed to download album art from {url}: {e}")
        return None

    async def _fetch_cover_art_from_track_id(self, track_id: str) -> Optional[str]:
        """Fetch album art using Spotify track ID via Open Graph scraping"""
        if not track_id or not track_id.startswith("spotify:track:"):
            return None

        spotify_id = track_id.split(":")[-1]

        # Try to get album art from Spotify's Open Graph meta tags
        # This doesn't require API auth
        try:
            import aiohttp
            url = f"https://open.spotify.com/track/{spotify_id}"

            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        html = await resp.text()

                        # Parse og:image meta tag
                        import re
                        match = re.search(r'<meta property="og:image" content="([^"]+)"', html)
                        if match:
                            image_url = match.group(1)
                            logging.info(f"Found album art URL from Open Graph: {image_url}")
                            return await self._download_cover_art(image_url)
                        else:
                            logging.warning("No og:image found in Spotify page")
        except Exception as e:
            logging.warning(f"Failed to fetch album art from track ID {spotify_id}: {e}")

        return None

    def _store_spotify_url(self, track_id: Optional[str]) -> None:
        """Extract Spotify URL from track ID"""
        if track_id:
            # Handle both spotify:track:ID and bare ID formats
            if track_id.startswith("spotify:track:"):
                spotify_id = track_id.split(":")[-1]
            else:
                spotify_id = track_id
            self.track_info["spotify_id"] = spotify_id
            self.track_info["spotify_url"] = f"https://open.spotify.com/track/{spotify_id}"

    async def _save_state(self) -> None:
        """Save current Spotify state to disk"""
        try:
            state = {
                "is_playing": self.is_playing,
                "is_session_connected": self.is_session_connected,
                "current_track_id": self.current_track_id,
                "track_info": self.track_info,
                "last_event": self.last_event,
                "last_event_time": self.last_event_time.isoformat() if self.last_event_time else None,
            }
            with open(self.STATE_FILE, "w") as f:
                json.dump(state, f)
            logging.debug(f"Saved Spotify state: {self.last_event}")
        except Exception as e:
            logging.warning(f"Failed to save Spotify state: {e}")

    async def _restore_state(self) -> None:
        """Restore Spotify state from disk if available"""
        try:
            if not Path(self.STATE_FILE).exists():
                logging.debug("No saved Spotify state found")
                return

            with open(self.STATE_FILE, "r") as f:
                state = json.load(f)

            self.is_playing = state.get("is_playing", False)
            self.is_session_connected = state.get("is_session_connected", False)
            self.current_track_id = state.get("current_track_id")
            self.track_info = state.get("track_info", {})
            self.last_event = state.get("last_event")

            if state.get("last_event_time"):
                self.last_event_time = datetime.fromisoformat(state["last_event_time"])

            logging.info(f"Restored Spotify state: {self.last_event} (is_playing={self.is_playing})")

        except Exception as e:
            logging.warning(f"Failed to restore Spotify state: {e}")

    def get_status(self) -> Dict[str, Any]:
        """Get current Spotify playback status"""
        return {
            "is_playing": self.is_playing,
            "is_session_connected": self.is_session_connected,
            "current_track_id": self.current_track_id,
            "track_info": self.track_info if self.track_info else None,
            "last_event": self.last_event,
            "last_event_time": self.last_event_time.isoformat() if self.last_event_time else None,
            "device_name": "HSG Canvas"
        }

    def is_active(self) -> bool:
        """Check if Spotify is currently active (playing or connected)"""
        return self.is_playing or self.is_session_connected
