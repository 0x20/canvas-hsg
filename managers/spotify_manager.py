"""
Spotify Manager

Handles Spotify Connect state tracking and drives the now-playing view.

Librespot 0.8 onevent flow:
  1. track_changed  — has NAME, ARTISTS, ALBUM, COVERS, DURATION_MS
  2. playing        — has TRACK_ID, POSITION_MS only
  3. paused/stopped — has TRACK_ID only
"""
import asyncio
import logging
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, Set

from managers.now_playing import track_payload


class SpotifyManager:
    """Manages Spotify Connect state and integration"""

    STATE_FILE = "/tmp/spotify_state.json"

    def __init__(self, websocket_manager=None):
        self.websocket_manager = websocket_manager
        self.ha_manager = None
        self.audio_conflict = None  # Set after creation in main.py
        self.display_stack = None  # Set after creation in main.py
        self.bluetooth_manager = None  # Set after creation in main.py
        self.sendspin_manager = None  # Set after creation in main.py

        # Current Spotify state
        self.is_playing = False
        # is_paused holds the now-playing view up (last card + art, pause
        # overlay) instead of reverting to the background when playback pauses.
        self.is_paused = False
        self.is_session_connected = False
        self.current_track_id: Optional[str] = None
        self.track_info: Dict[str, Any] = {}
        self.last_event: Optional[str] = None
        self.last_event_time: Optional[datetime] = None
        # What librespot itself does, even while another source mutes it.
        self._librespot_playing = False
        self._tasks: Set[asyncio.Task] = set()

    async def initialize(self):
        """Initialize and restore state from disk if available"""
        await self._restore_state()

        # Push to display stack if Spotify was playing when we last shut down
        if self.is_playing and self.track_info.get("name"):
            logging.info(f"Restored Spotify state: {self.track_info['name']} by {self.track_info.get('artists')}")
            logging.info(f"Spotify is playing - pushing to display stack")

            # Push spotify onto display stack so React shows now-playing
            if self.display_stack:
                await self.display_stack.push("spotify", {}, item_id="spotify")

            # Also broadcast track data and state for existing WebSocket listeners
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
            previous_event = self.last_event
            self.last_event = event
            self.last_event_time = datetime.now()

            logging.info(f"Spotify event: {event} (track_id={track_id}, name={name})")

            if event == "session_connected":
                self.is_session_connected = True
                logging.info("Spotify session connected")

            elif event == "track_changed":
                # track_changed carries all metadata: NAME, ARTISTS, ALBUM, COVERS, DURATION_MS
                self._librespot_playing = True
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

                # If another source pre-empted us, just store metadata silently
                if self._is_preempted():
                    logging.info(f"Spotify track_changed (pre-empted, metadata only): {name}")
                    await self._save_state()
                    return True

                await self._broadcast_track()
                # The "playing" event sometimes arrives late or not at all
                await self._show_playing()
                logging.info(f"Spotify track changed: {name} - {artists}")

            elif event == "playing":
                self._librespot_playing = True
                # librespot keeps firing events while another source holds the
                # audio. Only a resume after a pause or stop is a user action
                # that takes the audio back.
                user_resumed = previous_event in ("paused", "stopped")
                if self._is_preempted() and not user_resumed:
                    logging.info("Spotify playing event ignored (pre-empted by another source)")
                    return True

                # Don't update track_id from playing event - it can be stale/wrong
                # track_changed is the authoritative source for track changes
                if track_id and position_ms is not None:
                    self.track_info["position_ms"] = position_ms

                await self._show_playing()
                logging.info(f"Spotify now playing: {self.track_info.get('name', track_id)}")

            elif event == "paused":
                # Hold the now-playing view but mark it paused — keep the card,
                # album art and queue on screen with a pause overlay rather than
                # reverting to the background. A real stop still tears it down.
                self._librespot_playing = False
                self.is_playing = False
                self.is_paused = True
                logging.info("Spotify playback paused")

                # Release the audio lock so a paused stream doesn't leave
                # Sendspin muted.
                if self.audio_conflict:
                    await self.audio_conflict.release("spotify")

                # Keep spotify on the display stack (idempotent) so the view holds.
                if self.display_stack:
                    await self.display_stack.push("spotify", {}, item_id="spotify")

                # Overlay for the display; is_playing for the control panel.
                if self.websocket_manager:
                    await self.websocket_manager.broadcast("playback_state", {"paused": True})
                    await self.websocket_manager.broadcast("spotify_state", {"is_playing": False})

            elif event in ("stopped", "session_disconnected"):
                self._librespot_playing = False
                self.is_playing = False
                self.is_paused = False
                if event == "session_disconnected":
                    self.is_session_connected = False
                self.current_track_id = None
                self.track_info = {}
                logging.info(f"Spotify {event}")

                if self.audio_conflict:
                    await self.audio_conflict.release("spotify")

                # Remove spotify from display stack
                if self.display_stack:
                    await self.display_stack.remove_by_type("spotify")

                # Broadcast state change via WebSocket (React will switch views)
                if self.websocket_manager:
                    await self.websocket_manager.broadcast("spotify_state", {"is_playing": False})

            elif event == "volume_changed":
                logging.info("Spotify volume changed")

            else:
                logging.debug(f"Unhandled Spotify event: {event}")

            # Save state after each event
            await self._save_state()

            # Notify Home Assistant of state change
            if self.ha_manager:
                self._spawn(self.ha_manager.notify_state_change())

            return True

        except Exception as e:
            logging.error(f"Failed to handle Spotify event {event}: {e}")
            return False

    async def _show_playing(self) -> None:
        """Take the audio (first time only) and show the now-playing view."""
        if not self.is_playing:
            self.is_playing = True
            if self.audio_conflict:
                await self.audio_conflict.claim("spotify")

        # Push spotify onto display stack (auto-evicts BT/sendspin via EXCLUSIVE_TYPES)
        if self.display_stack:
            await self.display_stack.push("spotify", {}, item_id="spotify")
        if self.websocket_manager:
            await self.websocket_manager.broadcast("spotify_state", {"is_playing": True})
        await self._clear_paused()

    async def _broadcast_track(self) -> None:
        """Send the current track to the now-playing view."""
        if self.track_info.get("name") and self.websocket_manager:
            await self.websocket_manager.broadcast("track_changed", track_payload(self.track_info))

    def on_preempted(self) -> None:
        """Another source took the audio: Raspotify is muted, not stopped."""
        self.is_playing = False

    async def on_unmuted(self) -> None:
        """The source that muted us stopped. If librespot still plays, show it."""
        if self._librespot_playing and self.track_info.get("name") and not self._is_preempted():
            logging.info("Spotify audible again - showing now-playing")
            await self._broadcast_track()
            await self._show_playing()

    def _spawn(self, coro) -> None:
        """Run a fire-and-forget task and keep a reference until it ends."""
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _clear_paused(self) -> None:
        """Clear a paused overlay when playback resumes."""
        if not self.is_paused:
            return
        self.is_paused = False
        if self.websocket_manager:
            await self.websocket_manager.broadcast("playback_state", {"paused": False})

    def _is_preempted(self) -> bool:
        """Check if another audio source currently holds the audio or the display.

        When pre-empted, librespot still fires events but we should not
        push to the display stack or mute competitors.
        """
        if self.audio_conflict and self.audio_conflict.is_muted("raspotify"):
            return True
        if self.bluetooth_manager and self.bluetooth_manager.is_playing:
            return True
        if self.sendspin_manager and self.sendspin_manager.is_playing:
            return True
        return False

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
            self._librespot_playing = self.is_playing
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
