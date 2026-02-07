"""
Spotify Manager

Handles Spotify Connect state tracking and integration with audio playback.
Downloads album art and triggers "Now Playing" display on the physical screen.

Librespot 0.8 onevent flow:
  1. track_changed  — has NAME, ARTISTS, ALBUM, COVERS, DURATION_MS
  2. playing        — has TRACK_ID, POSITION_MS only
  3. paused/stopped — has TRACK_ID only
"""
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

    def __init__(self, audio_manager=None, background_manager=None):
        self.audio_manager = audio_manager
        self.background_manager = background_manager

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

        # If we restored a playing state, update the display
        if self.is_playing and self.track_info.get("name"):
            logging.info("Restoring Spotify now-playing display from saved state")
            await self._update_now_playing_display(
                self.track_info["name"],
                self.track_info.get("artists"),
                self.track_info.get("album"),
                None,  # Will use cached cover art if available
                skip_delete=True  # Don't delete cached album art during restoration
            )

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

                self._store_spotify_url(track_id)

                # Update now-playing display with metadata
                if name and self.background_manager:
                    await self._update_now_playing_display(name, artists, album, covers)

                logging.info(f"Spotify track changed: {name} - {artists}")

            elif event == "playing":
                was_playing = self.is_playing
                self.is_playing = True

                # Don't update track_id from playing event - it can be stale/wrong
                # track_changed is the authoritative source for track changes
                if track_id and position_ms is not None:
                    self.track_info["position_ms"] = position_ms

                # Stop audio playback when Spotify starts playing (only first time)
                if not was_playing and self.audio_manager:
                    logging.info("Spotify started playing - stopping audio streams")
                    await self.audio_manager.stop_audio_stream()

                # Only update display if we don't have metadata yet (edge case: playing before track_changed)
                # If track_changed already happened for ANY track, don't update display on playing
                if self.background_manager and self.track_info.get("name") and not was_playing:
                    # Only display if we haven't received track_changed yet (rare edge case)
                    if self.last_event != "track_changed":
                        await self._update_now_playing_display(
                            self.track_info["name"],
                            self.track_info.get("artists"),
                            self.track_info.get("album"),
                            None,  # cover already downloaded if available
                        )

                logging.info(f"Spotify now playing: {self.track_info.get('name', track_id)}")

            elif event == "paused":
                self.is_playing = False
                logging.info("Spotify playback paused")

            elif event in ("stopped", "session_disconnected"):
                self.is_playing = False
                if event == "session_disconnected":
                    self.is_session_connected = False
                self.current_track_id = None
                self.track_info = {}
                logging.info(f"Spotify {event}")

                # Restore default background
                if self.background_manager:
                    await self.background_manager.start_static_mode(force_redisplay=True)

            elif event == "volume_changed":
                logging.info("Spotify volume changed")

            else:
                logging.debug(f"Unhandled Spotify event: {event}")

            # Save state after each event
            await self._save_state()

            return True

        except Exception as e:
            logging.error(f"Failed to handle Spotify event {event}: {e}")
            return False

    async def _update_now_playing_display(self, name: str, artists: Optional[str],
                                          album: Optional[str], covers: Optional[str],
                                          skip_delete: bool = False) -> None:
        """Download album art and trigger the now-playing background display"""
        cover_path = None

        # Delete old album art to force fresh download (unless restoring same track)
        if not skip_delete:
            try:
                if Path(self.COVER_ART_PATH).exists():
                    Path(self.COVER_ART_PATH).unlink()
            except:
                pass

        # Try multiple methods to get album art
        if covers:
            # Method 1: Use COVERS URL from librespot (if provided)
            cover_path = await self._download_cover_art(covers)

        if not cover_path and self.current_track_id:
            # Method 2: Fetch from Spotify using track ID (via Open Graph)
            cover_path = await self._fetch_cover_art_from_track_id(self.current_track_id)

        # Only use cached art during state restoration (skip_delete=True) if we're restoring the same track
        if not cover_path and skip_delete and Path(self.COVER_ART_PATH).exists():
            # Cached art is only valid during state restoration
            cover_path = self.COVER_ART_PATH
            logging.info("Using cached album art for restored track")

        try:
            await self.background_manager.start_now_playing_mode(
                track_name=name,
                artists=artists or "Unknown Artist",
                album=album or "",
                album_art_path=cover_path,
            )
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
        if track_id and track_id.startswith("spotify:track:"):
            spotify_id = track_id.split(":")[-1]
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
