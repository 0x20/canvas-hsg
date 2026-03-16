"""
Sendspin Manager

Handles Sendspin integration for receiving music metadata and controlling
the display when the Sendspin daemon (systemd service) is playing audio
from Music Assistant.

Architecture:
- The sendspin daemon (systemd service) handles audio playback and MPRIS.
- It sends hook events (--hook-start / --hook-stop) to FastAPI endpoints.
- This manager reads track metadata from MPRIS via DBus (same session bus).
- Display and WebSocket updates use the same format as Spotify integration.
"""
import asyncio
import logging
import subprocess
from datetime import datetime
from typing import Any, Dict, Optional

from config import SENDSPIN_LISTENER_PORT

# DBus constants for MPRIS
_DBUS_ENV = {
    "DBUS_SESSION_BUS_ADDRESS": "unix:path=/run/user/1000/bus",
    "XDG_RUNTIME_DIR": "/run/user/1000",
}
_MPRIS_DEST_PREFIX = "org.mpris.MediaPlayer2.Sendspin"


class SendspinManager:
    """Manages Sendspin display integration via daemon hooks and MPRIS."""

    def __init__(self, audio_manager=None, websocket_manager=None, audio_conflict=None):
        self.audio_manager = audio_manager
        self.websocket_manager = websocket_manager
        self.audio_conflict = audio_conflict
        self.playback_manager = None
        self.spotify_manager = None
        self.bluetooth_manager = None
        self.display_stack = None

        # Current state
        self.is_playing = False
        self.is_connected = False
        self.track_info: Dict[str, Any] = {}
        self.last_event_time: Optional[datetime] = None
        self.group_name: Optional[str] = None

        # Metadata polling task
        self._poll_task: Optional[asyncio.Task] = None

    async def initialize(self) -> None:
        """Check if sendspin daemon is running."""
        try:
            result = subprocess.run(
                ["systemctl", "is-active", "sendspin"],
                capture_output=True, text=True, timeout=5,
            )
            if result.stdout.strip() == "active":
                self.is_connected = True
                logging.info("Sendspin daemon is active, waiting for hook events")
            else:
                logging.info("Sendspin daemon not active, will respond to hook events when started")
        except Exception as e:
            logging.warning(f"Could not check sendspin daemon status: {e}")

    async def cleanup(self) -> None:
        """Clean up state."""
        try:
            if self._poll_task and not self._poll_task.done():
                self._poll_task.cancel()
            # Restore any muted sources
            if self.audio_conflict:
                await self.audio_conflict.unmute_source("raspotify")
            logging.info("Sendspin manager cleaned up")
        except Exception as e:
            logging.error(f"Error during Sendspin cleanup: {e}")

    async def handle_hook_start(self) -> None:
        """Called when sendspin daemon starts audio playback (hook-start)."""
        logging.info("Sendspin hook: stream started")
        self.is_connected = True
        was_playing = self.is_playing
        self.is_playing = True

        if not was_playing:
            # Mute Raspotify (last-in wins)
            if self.audio_conflict:
                await self.audio_conflict.mute_source("raspotify")

            # Pause Bluetooth AVRCP
            if hasattr(self, 'bluetooth_manager') and self.bluetooth_manager:
                await self.bluetooth_manager.pause_playback()

            # Stop any local audio/video playback
            if self.audio_manager:
                await self.audio_manager.stop_audio_stream()
            if self.playback_manager:
                await self.playback_manager.stop_playback()

            # Push to display stack
            if self.display_stack:
                await self.display_stack.push("sendspin", {}, item_id="sendspin")

            # Broadcast playing state
            if self.websocket_manager:
                await self.websocket_manager.broadcast("spotify_state", {
                    "is_playing": True,
                })

        # Read metadata from MPRIS and broadcast
        await self._read_and_broadcast_metadata()

        # Start polling for metadata changes
        self._start_metadata_polling()

    async def handle_hook_stop(self) -> None:
        """Called when sendspin daemon stops audio playback (hook-stop)."""
        logging.info("Sendspin hook: stream stopped")
        was_playing = self.is_playing
        self.is_playing = False

        # Stop metadata polling
        self._stop_metadata_polling()

        if was_playing:
            # Unmute Raspotify
            if self.audio_conflict:
                await self.audio_conflict.unmute_source("raspotify")

        # Remove from display stack
        if self.display_stack:
            await self.display_stack.remove_by_type("sendspin")

        # Broadcast stopped state
        if self.websocket_manager:
            await self.websocket_manager.broadcast("spotify_state", {
                "is_playing": False,
            })

        self.track_info = {}

    def _start_metadata_polling(self) -> None:
        """Start polling MPRIS for metadata changes (track changes)."""
        self._stop_metadata_polling()
        self._poll_task = asyncio.create_task(self._metadata_poll_loop())

    def _stop_metadata_polling(self) -> None:
        """Stop the metadata polling loop."""
        if self._poll_task and not self._poll_task.done():
            self._poll_task.cancel()
            self._poll_task = None

    async def _metadata_poll_loop(self) -> None:
        """Poll MPRIS every few seconds for metadata changes."""
        try:
            while self.is_playing:
                await self._read_and_broadcast_metadata()
                await asyncio.sleep(5)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logging.error(f"Sendspin metadata poll error: {e}")

    async def _read_and_broadcast_metadata(self) -> None:
        """Read current track metadata from MPRIS and broadcast if changed."""
        metadata = await self._read_mpris_metadata()
        if not metadata:
            return

        title = metadata.get("xesam:title")
        if not title:
            return

        artists = metadata.get("xesam:artist", ["Unknown Artist"])
        artist_str = ", ".join(artists) if isinstance(artists, list) else str(artists)
        album = metadata.get("xesam:album", "")
        artwork_url = metadata.get("mpris:artUrl")
        duration_us = metadata.get("mpris:length", 0)
        duration_ms = duration_us // 1000 if duration_us else 0

        new_info = {
            "name": title,
            "artists": artist_str,
            "album": album or "",
            "album_art_url": artwork_url,
            "duration_ms": duration_ms,
        }

        # Only broadcast if track changed
        if new_info.get("name") != self.track_info.get("name") or \
           new_info.get("artists") != self.track_info.get("artists"):
            self.track_info = new_info
            self.last_event_time = datetime.now()

            if self.websocket_manager:
                await self.websocket_manager.broadcast("track_changed", {
                    "name": self.track_info["name"],
                    "artists": self.track_info["artists"],
                    "album": self.track_info["album"],
                    "album_art_url": self.track_info.get("album_art_url"),
                    "duration_ms": self.track_info.get("duration_ms", 0),
                    "spotify_url": None,
                })
                logging.info(
                    f"Sendspin track: {self.track_info['name']} - {self.track_info['artists']}"
                )

    async def _read_mpris_metadata(self) -> Optional[Dict[str, Any]]:
        """Read metadata from the sendspin MPRIS interface via dbus-send."""
        try:
            # Find the sendspin MPRIS bus name (includes PID suffix)
            dest = await self._find_mpris_dest()
            if not dest:
                return None

            import os
            env = {**os.environ, **_DBUS_ENV}

            proc = await asyncio.create_subprocess_exec(
                "dbus-send", "--session", "--print-reply",
                f"--dest={dest}",
                "/org/mpris/MediaPlayer2",
                "org.freedesktop.DBus.Properties.Get",
                "string:org.mpris.MediaPlayer2.Player",
                "string:Metadata",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=3)

            if proc.returncode != 0:
                return None

            return _parse_dbus_metadata(stdout.decode())
        except asyncio.TimeoutError:
            return None
        except Exception as e:
            logging.debug(f"MPRIS read error: {e}")
            return None

    async def _find_mpris_dest(self) -> Optional[str]:
        """Find the sendspin MPRIS bus name on DBus."""
        try:
            import os
            env = {**os.environ, **_DBUS_ENV}

            proc = await asyncio.create_subprocess_exec(
                "dbus-send", "--session", "--print-reply",
                "--dest=org.freedesktop.DBus",
                "/org/freedesktop/DBus",
                "org.freedesktop.DBus.ListNames",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=3)

            for line in stdout.decode().split("\n"):
                line = line.strip()
                if _MPRIS_DEST_PREFIX in line:
                    # Extract the bus name from the dbus-send output
                    start = line.find('"')
                    end = line.rfind('"')
                    if start >= 0 and end > start:
                        return line[start + 1:end]
            return None
        except Exception:
            return None

    def get_status(self) -> Dict[str, Any]:
        """Get current Sendspin status for the API."""
        return {
            "is_connected": self.is_connected,
            "is_playing": self.is_playing,
            "group_name": self.group_name,
            "track_info": self.track_info or None,
            "last_event_time": self.last_event_time.isoformat() if self.last_event_time else None,
            "listener_port": SENDSPIN_LISTENER_PORT,
        }


def _parse_dbus_metadata(output: str) -> Dict[str, Any]:
    """Parse dbus-send metadata output into a dict.

    Handles the common MPRIS metadata fields:
    - string values (xesam:title, xesam:album, mpris:artUrl)
    - array of strings (xesam:artist)
    - int64 values (mpris:length)
    """
    metadata = {}
    lines = output.split("\n")
    i = 0
    current_key = None

    while i < len(lines):
        line = lines[i].strip()

        if 'dict entry(' in line:
            current_key = None
        elif 'string "' in line and current_key is None:
            # This is a dict key
            start = line.find('"') + 1
            end = line.rfind('"')
            if start > 0 and end > start:
                current_key = line[start:end]
        elif current_key and 'string "' in line:
            # String value
            start = line.find('"') + 1
            end = line.rfind('"')
            if start > 0 and end > start:
                metadata[current_key] = line[start:end]
            current_key = None
        elif current_key and 'int64 ' in line:
            # Integer value
            parts = line.split()
            for part in parts:
                try:
                    metadata[current_key] = int(part)
                    break
                except ValueError:
                    continue
            current_key = None
        elif current_key and 'array [' in line:
            # Array value — collect strings
            arr = []
            i += 1
            while i < len(lines) and ']' not in lines[i]:
                aline = lines[i].strip()
                if 'string "' in aline:
                    start = aline.find('"') + 1
                    end = aline.rfind('"')
                    if start > 0 and end > start:
                        arr.append(aline[start:end])
                i += 1
            metadata[current_key] = arr
            current_key = None
        elif current_key and 'object path "' in line:
            start = line.find('"') + 1
            end = line.rfind('"')
            if start > 0 and end > start:
                metadata[current_key] = line[start:end]
            current_key = None

        i += 1

    return metadata
