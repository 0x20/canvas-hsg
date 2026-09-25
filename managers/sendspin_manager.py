"""
Sendspin Manager

Handles Sendspin integration for receiving music metadata and controlling
the display when the Sendspin daemon (systemd service) is playing audio
from Music Assistant.

Architecture:
- The sendspin daemon (systemd service) handles audio playback and MPRIS.
- It sends hook events (--hook-start / --hook-stop) to FastAPI endpoints.
- The artwork display client (CONTROLLER+METADATA+ARTWORK roles) receives the
  playing group's track metadata and cover art from Music Assistant — this is
  the preferred now-playing source, and it works even when the audio renders
  on another speaker in the space (the display just joins the playing group).
- MPRIS via DBus is the fallback metadata source for local-only playback.
- Display and WebSocket updates use the same format as Spotify integration.
"""
import asyncio
import logging
import os
from datetime import datetime
from typing import Any, Dict, Optional

from config import SENDSPIN_LISTENER_PORT
from utils.proc import run

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

    def __init__(self, websocket_manager=None, audio_conflict=None):
        self.websocket_manager = websocket_manager
        self.audio_conflict = audio_conflict
        self.display_stack = None
        # Sendspin ARTWORK-role display client (provides album art over the LAN).
        self.artwork_client = None

        # Current state. is_playing means "the now-playing view is active";
        # _local_audio means audio is actually rendering on this Pi (drives the
        # audio-exclusivity actions, which a remote-speaker display must skip).
        self.is_playing = False
        # is_paused means "the now-playing view is held, but paused" — the queue
        # is stopped rather than gone, so we keep the last card + album art up
        # with a pause overlay instead of reverting to the background.
        self.is_paused = False
        self._local_audio = False
        # Another source holds the audio. The watcher must not take it back;
        # only a new hook-start or the end of that source clears this.
        self._preempted = False
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
        _, out = await run("systemctl", "is-active", "sendspin")
        if out.strip() == "active":
            self.is_connected = True
            logging.info("Sendspin daemon is active, waiting for hook events")
        else:
            logging.info("Sendspin daemon not active, will respond to hook events when started")

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
                await self.audio_conflict.release("sendspin")
            logging.info("Sendspin manager cleaned up")
        except Exception as e:
            logging.error(f"Error during Sendspin cleanup: {e}")

    async def handle_hook_start(self, local: bool = True) -> None:
        """Show the now-playing view.

        Called by the daemon's hook-start (local audio) and by the playback
        watcher — with local=False when the music plays on another speaker in
        the space (then the audio-exclusivity actions must not run: nothing is
        rendering here, so there's nothing to stop or mute).
        """
        logging.info("Sendspin: stream started (%s)", "local" if local else "remote group")
        # Only the daemon hook calls this while pre-empted: a new stream start
        # is a user action and takes the audio back.
        self._preempted = False
        self.is_connected = True
        was_showing = self.is_playing or self.is_paused
        was_paused = self.is_paused
        self.is_paused = False
        self.is_playing = True

        if local and not self._local_audio:
            self._local_audio = True

            # Stop, pause or mute every other audio source (last-in wins)
            if self.audio_conflict:
                await self.audio_conflict.claim("sendspin")

        if not was_showing:
            # Push to display stack
            if self.display_stack:
                await self.display_stack.push("sendspin", {}, item_id="sendspin")

            # Broadcast playing state
            if self.websocket_manager:
                await self.websocket_manager.broadcast("spotify_state", {
                    "is_playing": True,
                })

        # Read metadata and broadcast
        await self._read_and_broadcast_metadata()

        # Coming out of pause: clear the paused overlay on the now-playing view.
        if was_paused and self.websocket_manager:
            await self.websocket_manager.broadcast("playback_state", {"paused": False})

        # Start polling for metadata changes
        self._start_metadata_polling()

    def _remote_group_playing(self) -> bool:
        """True when MA reports our group playing with a known track —
        i.e. there is music in the space worth displaying, regardless of
        which speaker renders it."""
        ac = self.artwork_client
        return bool(ac and ac.group_playing and ac.track_title)

    def _remote_group_paused(self) -> bool:
        """True when MA reports our group paused with a known track — a held
        queue we should keep showing (paused), not a stop."""
        ac = self.artwork_client
        return bool(ac and ac.group_paused and ac.track_title)

    def on_preempted(self) -> None:
        """Another source took the audio: the Sendspin sink is muted."""
        self._preempted = True
        self._local_audio = False
        self.is_playing = False

    def on_unmuted(self) -> None:
        """The source that muted us stopped; the watcher may show us again."""
        self._preempted = False

    async def handle_hook_stop(self) -> None:
        """Called when sendspin daemon stops audio playback (hook-stop)."""
        logging.info("Sendspin hook: stream stopped")
        if self._local_audio:
            self._local_audio = False
            # Unmute Raspotify
            if self.audio_conflict:
                await self.audio_conflict.release("sendspin")

        # If the group keeps playing on another speaker, keep displaying it.
        if self._remote_group_playing():
            logging.info("Sendspin: local stream stopped but group still playing — keeping now-playing")
            return

        # A local pause stops the stream (the daemon fires hook-stop) while MA
        # keeps the queue paused. Hold the view and show it paused rather than
        # reverting to the background.
        if self._remote_group_paused():
            logging.info("Sendspin: local stream stopped but group paused — showing paused")
            await self.handle_pause()
            return

        await self._hide_now_playing()

    async def handle_pause(self) -> None:
        """Hold the now-playing view but mark it paused.

        Unlike a stop, the MA queue is only held — so we keep the last card and
        album art on screen with a pause overlay, and re-show playing as soon as
        playback resumes (handled by the playback watcher / hook-start).
        """
        if self.is_paused:
            return
        logging.info("Sendspin: playback paused — holding now-playing view")
        self.is_paused = True
        self.is_playing = False

        # Release local audio ownership so a paused stream doesn't leave
        # Raspotify muted.
        if self._local_audio:
            self._local_audio = False
            if self.audio_conflict:
                await self.audio_conflict.release("sendspin")

        # Nothing changes while paused; the watcher keeps running and re-shows on
        # resume. Keep the card on the display stack (idempotent) so the view
        # holds even if a hook-stop popped it before we knew MA was only paused.
        self._stop_metadata_polling()
        if self.display_stack:
            await self.display_stack.push("sendspin", {}, item_id="sendspin")

        if self.websocket_manager:
            await self.websocket_manager.broadcast("playback_state", {"paused": True})

    async def _hide_now_playing(self) -> None:
        """Tear down the now-playing view and broadcast the stopped state."""
        self.is_playing = False
        self.is_paused = False

        # Stop metadata polling
        self._stop_metadata_polling()

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
        """Poll for metadata changes (track changes) while the view is up.
        Group syncing lives in the playback watcher, which always runs."""
        try:
            while self.is_playing:
                await self._read_and_broadcast_metadata()
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
        """Read the current track and broadcast if changed.

        Single source-selection point for the now-playing view: prefer the
        artwork client's group metadata from Music Assistant (carries artwork,
        and exists even when the audio renders elsewhere), falling back to the
        local daemon's MPRIS for local-only playback.
        """
        new_info = self._track_from_artwork_client() or await self._track_from_mpris()
        if not new_info:
            return

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

    def _track_from_artwork_client(self) -> Optional[Dict[str, Any]]:
        """Now-playing dict from MA's group metadata, or None if unavailable."""
        ac = self.artwork_client
        if not (ac and ac.group_playing and ac.track_title):
            return None
        return {
            "name": ac.track_title,
            "artists": ac.track_artist or "Unknown Artist",
            "album": ac.track_album or "",
            "album_art_url": ac.art_url,
            "duration_ms": ac.track_duration_ms or 0,
        }

    async def _track_from_mpris(self) -> Optional[Dict[str, Any]]:
        """Now-playing dict from the local daemon's MPRIS, or None."""
        metadata = await self._read_mpris_metadata()
        if not metadata:
            return None

        title = metadata.get("xesam:title")
        if not title:
            return None

        artists = metadata.get("xesam:artist", ["Unknown Artist"])
        artist_str = ", ".join(artists) if isinstance(artists, list) else str(artists)
        album = metadata.get("xesam:album", "")
        # Album art comes from the Sendspin ARTWORK display client (binary frames
        # from Music Assistant over the LAN), not MPRIS (the audio daemon's MPRIS
        # doesn't carry artwork). Fall back to MPRIS artUrl if ever present.
        artwork_url = self._current_art_url() or metadata.get("mpris:artUrl")
        duration_us = metadata.get("mpris:length", 0)
        duration_ms = duration_us // 1000 if duration_us else 0

        return {
            "name": title,
            "artists": artist_str,
            "album": album or "",
            "album_art_url": artwork_url,
            "duration_ms": duration_ms,
        }

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
        """Reconcile the now-playing view with actual playback, independent of
        the hooks.

        The daemon's --hook-start only fires on stream start (stopped→playing),
        so it misses track changes within a stream and any playback already in
        progress when hsg-canvas (re)starts. And music playing on *another*
        speaker never touches the local daemon at all — it's only visible via
        the artwork client's group state, which this loop keeps synced to the
        playing group. Polling both sources makes the display self-heal to the
        real state of the space.
        """
        while True:
            try:
                await asyncio.sleep(4)

                # Keep the artwork display in the playing group so MA pushes
                # it per-track metadata + covers. No-op once joined; rate-
                # limited internally when nothing is playing.
                if self.artwork_client:
                    await self.artwork_client.sync_to_playing_group()

                status = await self._read_mpris_playback_status()
                local = status == "Playing"
                stopped_local = status == "Stopped"
                remote = self._remote_group_playing()
                remote_paused = self._remote_group_paused()

                if self._preempted:
                    # Another source holds the audio and the display.
                    pass
                elif local or remote:
                    # Music is playing somewhere (this Pi or another speaker) —
                    # show it, clearing any paused overlay.
                    if not self.is_playing:
                        logging.info("Sendspin: playback detected — showing now-playing")
                        await self.handle_hook_start(local=local)
                    elif local and not self._local_audio:
                        # View already up but audio is local again (e.g. resumed
                        # after a remote-first tick) — re-acquire the audio lock.
                        await self.handle_hook_start(local=True)
                elif status == "Paused" or remote_paused:
                    # Paused, nothing playing → hold the view and show paused.
                    if not self.is_paused:
                        logging.info(f"Sendspin: playback paused (mpris={status}) — showing paused")
                        await self.handle_pause()
                elif self._local_audio and stopped_local:
                    # Local stream explicitly stopped. handle_hook_stop re-checks
                    # MA and downgrades to paused if the queue is only held.
                    logging.info("Sendspin: local stream stopped via MPRIS")
                    await self.handle_hook_stop()
                elif not self._local_audio and (self.is_playing or self.is_paused) \
                        and self.artwork_client and not remote and not remote_paused:
                    # A remote/paused view whose MA group is neither playing nor
                    # paused → really stopped. MA group state is event-driven, so
                    # this isn't a transient MPRIS read blip.
                    logging.info("Sendspin: group stopped — hiding now-playing")
                    await self._hide_now_playing()
                elif self.is_paused and not self.artwork_client and stopped_local:
                    # MPRIS-only paused view that then explicitly stopped.
                    logging.info("Sendspin: paused stream stopped via MPRIS — hiding")
                    await self._hide_now_playing()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logging.debug(f"Sendspin playback watch error: {e}")

    def get_status(self) -> Dict[str, Any]:
        """Get current Sendspin status for the API."""
        ac = self.artwork_client
        return {
            "is_connected": self.is_connected,
            "is_playing": self.is_playing,
            "is_paused": self.is_paused,
            "local_audio": self._local_audio,
            "group_name": (ac.group_name if ac else None) or self.group_name,
            "group_playing": bool(ac and ac.group_playing),
            "group_paused": bool(ac and ac.group_paused),
            "track_info": self.track_info or None,
            "last_event_time": self.last_event_time.isoformat() if self.last_event_time else None,
            "listener_port": SENDSPIN_LISTENER_PORT,
            # PIN to enter in Music Assistant while the art client waits for pairing
            "pairing_pin": ac.pairing_pin if ac else None,
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
