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
import os
import subprocess
from datetime import datetime
from typing import Any, Dict, Optional

from config import SENDSPIN_LISTENER_PORT

# DBus constants for MPRIS. Derive the runtime dir from the running user so the
# session bus resolves on any uid (falls back to XDG_RUNTIME_DIR if set).
_RUNTIME_DIR = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
_DBUS_ENV = {
    "DBUS_SESSION_BUS_ADDRESS": os.environ.get(
        "DBUS_SESSION_BUS_ADDRESS", f"unix:path={_RUNTIME_DIR}/bus"
    ),
    "XDG_RUNTIME_DIR": _RUNTIME_DIR,
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
        # Sendspin ARTWORK-role display client (provides album art over the LAN).
        self.artwork_client = None

        # Current state
        self.is_playing = False
        self.is_connected = False
        self.track_info: Dict[str, Any] = {}
        self.last_event_time: Optional[datetime] = None
        self.group_name: Optional[str] = None

        # Metadata polling task
        self._poll_task: Optional[asyncio.Task] = None
        # Self-healing playback-state watcher (MPRIS PlaybackStatus) — covers
        # hooks missed across a restart or track changes within a stream.
        self._playback_watch_task: Optional[asyncio.Task] = None
        # Cached MPRIS bus name; re-discovered only when a read fails (daemon
        # restart), so polling doesn't spawn a ListNames subprocess each tick.
        self._mpris_dest: Optional[str] = None

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

        # Start the self-healing playback watcher so the now-playing view
        # reflects actual playback even when a hook is missed.
        if self._playback_watch_task is None or self._playback_watch_task.done():
            self._playback_watch_task = asyncio.create_task(self._playback_watch_loop())

    async def cleanup(self) -> None:
        """Clean up state."""
        try:
            if self._poll_task and not self._poll_task.done():
                self._poll_task.cancel()
            if self._playback_watch_task and not self._playback_watch_task.done():
                self._playback_watch_task.cancel()
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

            # Tell Spotify to clean up its is_playing state
            if hasattr(self, 'spotify_manager') and self.spotify_manager and self.spotify_manager.is_playing:
                self.spotify_manager.is_playing = False

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
                # Keep the artwork display in the speaker's (playing) group so MA
                # pushes it per-track covers. No-op once joined / unsupported, so
                # it's safe to call every tick; also covers a late MA connect.
                if self.artwork_client:
                    await self.artwork_client.sync_to_playing_group()
                await asyncio.sleep(5)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logging.error(f"Sendspin metadata poll error: {e}")

    def _current_art_url(self):
        """Album art URL from the Sendspin artwork display client, or None."""
        ac = self.artwork_client
        return ac.art_url if ac is not None else None

    async def on_artwork_updated(self) -> None:
        """Re-broadcast the current track with fresh album art.

        Called when the artwork display client receives a new cover frame. The
        metadata poll dedupes on track name/artist, so an art-only change would
        otherwise not reach the now-playing view until the next track change.
        """
        if not self.is_playing or not self.track_info or not self.websocket_manager:
            return
        self.track_info["album_art_url"] = self._current_art_url()
        await self.websocket_manager.broadcast("track_changed", {
            "name": self.track_info.get("name"),
            "artists": self.track_info.get("artists"),
            "album": self.track_info.get("album", ""),
            "album_art_url": self.track_info.get("album_art_url"),
            "duration_ms": self.track_info.get("duration_ms", 0),
            "spotify_url": None,
        })
        logging.info("Sendspin album art updated → %s", self._current_art_url())

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
        # Album art comes from the Sendspin ARTWORK display client (binary frames
        # from Music Assistant over the LAN), not MPRIS (the audio daemon's MPRIS
        # doesn't carry artwork). Fall back to MPRIS artUrl if ever present.
        artwork_url = self._current_art_url() or metadata.get("mpris:artUrl")
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
                self._mpris_dest = None  # stale dest (e.g. daemon restart) → re-discover
                return None

            return _parse_dbus_metadata(stdout.decode())
        except asyncio.TimeoutError:
            return None
        except Exception as e:
            logging.debug(f"MPRIS read error: {e}")
            return None

    async def _find_mpris_dest(self) -> Optional[str]:
        """Find (and cache) the sendspin MPRIS bus name on DBus.

        The bus name has a per-process suffix, so it's cached and only
        re-discovered when a read against it fails (e.g. daemon restart) —
        avoiding a ListNames subprocess on every poll tick.
        """
        if self._mpris_dest:
            return self._mpris_dest
        try:
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
                        self._mpris_dest = line[start + 1:end]
                        return self._mpris_dest
            return None
        except Exception:
            return None

    async def _read_mpris_playback_status(self) -> Optional[str]:
        """Read MPRIS PlaybackStatus (Playing/Paused/Stopped) from the daemon."""
        try:
            dest = await self._find_mpris_dest()
            if not dest:
                return None
            env = {**os.environ, **_DBUS_ENV}
            proc = await asyncio.create_subprocess_exec(
                "dbus-send", "--session", "--print-reply",
                f"--dest={dest}",
                "/org/mpris/MediaPlayer2",
                "org.freedesktop.DBus.Properties.Get",
                "string:org.mpris.MediaPlayer2.Player",
                "string:PlaybackStatus",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=3)
            if proc.returncode != 0:
                self._mpris_dest = None  # stale dest (e.g. daemon restart) → re-discover
                return None
            out = stdout.decode()
            # Reply looks like:  variant       string "Playing"
            if 'string "' in out:
                return out.rsplit('string "', 1)[1].split('"')[0]
            return None
        except asyncio.TimeoutError:
            return None
        except Exception as e:
            logging.debug(f"MPRIS PlaybackStatus read error: {e}")
            return None

    async def _playback_watch_loop(self) -> None:
        """Show/hide the now-playing view based on the daemon's MPRIS
        PlaybackStatus, independent of the hooks.

        The daemon's --hook-start only fires on stream start (stopped→playing),
        so it misses track changes within a stream and any playback already in
        progress when hsg-canvas (re)starts. Polling PlaybackStatus makes the
        display self-heal to the real state.
        """
        while True:
            try:
                await asyncio.sleep(4)
                status = await self._read_mpris_playback_status()
                if status == "Playing" and not self.is_playing:
                    logging.info("Sendspin playback detected via MPRIS — showing now-playing")
                    await self.handle_hook_start()
                elif status in ("Stopped", "Paused") and self.is_playing:
                    # Paused counts as not-actively-playing: hide the view and
                    # (via handle_hook_stop) unmute raspotify so a paused stream
                    # doesn't leave Spotify muted. Resume re-shows within a tick.
                    # status None is left alone — likely a transient read failure.
                    logging.info(f"Sendspin playback {status} via MPRIS — hiding now-playing")
                    await self.handle_hook_stop()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logging.debug(f"Sendspin playback watch error: {e}")

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
