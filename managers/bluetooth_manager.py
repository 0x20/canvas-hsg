"""
Bluetooth A2DP Sink Manager

Handles Bluetooth audio streaming from paired phones via BlueZ A2DP.
Track metadata comes from AVRCP (org.bluez.MediaPlayer1.Track).
Follows the same poll-based pattern as SendspinManager.

Architecture:
- BlueZ handles pairing and A2DP audio routing through PipeWire.
- This manager polls the system D-Bus for MediaPlayer1 objects.
- Display and WebSocket updates use the same format as Spotify/Sendspin.
"""
import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, Optional


class BluetoothManager:
    """Manages Bluetooth A2DP display integration via BlueZ D-Bus polling."""

    def __init__(self, audio_manager=None, websocket_manager=None, audio_conflict=None):
        self.audio_manager = audio_manager
        self.websocket_manager = websocket_manager
        self.audio_conflict = audio_conflict
        self.playback_manager = None
        self.spotify_manager = None
        self.sendspin_manager = None
        self.display_stack = None

        # Current state
        self.is_playing = False
        self.device_name: Optional[str] = None
        self.track_info: Dict[str, Any] = {}
        self.last_event_time: Optional[datetime] = None

        # Poll loop task
        self._poll_task: Optional[asyncio.Task] = None

    async def initialize(self) -> None:
        """Start the BlueZ D-Bus polling loop."""
        self._poll_task = asyncio.create_task(self._poll_loop())
        logging.info("Bluetooth manager initialized, polling for A2DP connections")

    async def cleanup(self) -> None:
        """Stop polling and clean up state."""
        try:
            if self._poll_task and not self._poll_task.done():
                self._poll_task.cancel()
            if self.is_playing:
                await self._handle_disconnect()
            logging.info("Bluetooth manager cleaned up")
        except Exception as e:
            logging.error(f"Error during Bluetooth cleanup: {e}")

    async def pause_playback(self) -> None:
        """Pause Bluetooth playback via AVRCP D-Bus method."""
        if not self.is_playing:
            return
        try:
            player_path = await self._find_media_player_path()
            if not player_path:
                return

            proc = await asyncio.create_subprocess_exec(
                "dbus-send", "--system", "--print-reply",
                f"--dest=org.bluez",
                player_path,
                "org.bluez.MediaPlayer1.Pause",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(proc.communicate(), timeout=3)
            logging.info("Sent AVRCP Pause to Bluetooth device")
        except Exception as e:
            logging.warning(f"Failed to send AVRCP Pause: {e}")

    async def _poll_loop(self) -> None:
        """Poll BlueZ D-Bus every 3 seconds for MediaPlayer1 objects."""
        try:
            while True:
                try:
                    await self._poll_bluez()
                except Exception as e:
                    logging.debug(f"Bluetooth poll error: {e}")
                await asyncio.sleep(3)
        except asyncio.CancelledError:
            pass

    async def _poll_bluez(self) -> None:
        """Single poll iteration: check for MediaPlayer1 and read metadata."""
        managed_objects = await self._get_managed_objects()
        if managed_objects is None:
            return

        player_path = None
        player_status = None
        device_path = None

        for obj_path, interfaces in managed_objects.items():
            if "org.bluez.MediaPlayer1" in interfaces:
                player_path = obj_path
                player_props = interfaces["org.bluez.MediaPlayer1"]
                player_status = player_props.get("Status", "").lower()
                # Device path is parent of player (e.g. /org/bluez/hci0/dev_XX_XX/player0 -> /org/bluez/hci0/dev_XX_XX)
                device_path = "/".join(obj_path.split("/")[:-1])
                break

        if player_path and player_status == "playing":
            if not self.is_playing:
                # Read device name
                device_alias = None
                if device_path and device_path in managed_objects:
                    dev_props = managed_objects[device_path].get("org.bluez.Device1", {})
                    device_alias = dev_props.get("Alias")
                await self._handle_connect(device_alias)

            # Read track metadata
            player_props = managed_objects[player_path].get("org.bluez.MediaPlayer1", {})
            await self._read_and_broadcast_track(player_props)

        elif self.is_playing:
            # Player gone or not playing anymore
            await self._handle_disconnect()

    async def _handle_connect(self, device_name: Optional[str] = None) -> None:
        """Handle a new Bluetooth A2DP connection starting playback."""
        logging.info(f"Bluetooth A2DP connected: {device_name or 'Unknown device'}")
        self.is_playing = True
        self.device_name = device_name

        # Mute competing sources
        if self.audio_conflict:
            await self.audio_conflict.mute_source("raspotify")
            await self.audio_conflict.mute_source("sendspin")

        # Stop local audio/video
        if self.audio_manager:
            await self.audio_manager.stop_audio_stream()
        if self.playback_manager:
            await self.playback_manager.stop_playback()

        # Push to display stack
        if self.display_stack:
            await self.display_stack.push("bluetooth", {}, item_id="bluetooth")

        # Broadcast playing state
        if self.websocket_manager:
            await self.websocket_manager.broadcast("spotify_state", {
                "is_playing": True,
            })

    async def _handle_disconnect(self) -> None:
        """Handle Bluetooth A2DP disconnection or playback stop."""
        logging.info("Bluetooth A2DP disconnected")
        was_playing = self.is_playing
        self.is_playing = False
        self.device_name = None
        self.track_info = {}

        if was_playing:
            # Unmute competing sources
            if self.audio_conflict:
                await self.audio_conflict.unmute_source("raspotify")
                await self.audio_conflict.unmute_source("sendspin")

        # Remove from display stack
        if self.display_stack:
            await self.display_stack.remove_by_type("bluetooth")

        # Broadcast stopped state
        if self.websocket_manager:
            await self.websocket_manager.broadcast("spotify_state", {
                "is_playing": False,
            })

    async def _read_and_broadcast_track(self, player_props: Dict[str, Any]) -> None:
        """Read AVRCP track metadata and broadcast if changed."""
        track = player_props.get("Track", {})
        if not track:
            return

        title = track.get("Title", "")
        if not title:
            return

        artist = track.get("Artist", "Unknown Artist")
        album = track.get("Album", "")
        duration_us = track.get("Duration", 0)
        duration_ms = duration_us // 1000 if duration_us else 0

        new_info = {
            "name": title,
            "artists": artist,
            "album": album,
            "album_art_url": None,
            "duration_ms": duration_ms,
        }

        # Only broadcast if track changed
        if new_info["name"] != self.track_info.get("name") or \
           new_info["artists"] != self.track_info.get("artists"):
            self.track_info = new_info
            self.last_event_time = datetime.now()

            if self.websocket_manager:
                await self.websocket_manager.broadcast("track_changed", {
                    "name": self.track_info["name"],
                    "artists": self.track_info["artists"],
                    "album": self.track_info["album"],
                    "album_art_url": None,
                    "duration_ms": self.track_info["duration_ms"],
                    "spotify_url": None,
                })
                logging.info(
                    f"Bluetooth track: {self.track_info['name']} - {self.track_info['artists']}"
                )

    async def _find_media_player_path(self) -> Optional[str]:
        """Find the first MediaPlayer1 object path from BlueZ."""
        managed_objects = await self._get_managed_objects()
        if not managed_objects:
            return None
        for obj_path, interfaces in managed_objects.items():
            if "org.bluez.MediaPlayer1" in interfaces:
                return obj_path
        return None

    async def _get_managed_objects(self) -> Optional[Dict[str, Dict[str, Any]]]:
        """Call GetManagedObjects on BlueZ and parse the output."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "dbus-send", "--system", "--print-reply",
                "--dest=org.bluez",
                "/",
                "org.freedesktop.DBus.ObjectManager.GetManagedObjects",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=3)

            if proc.returncode != 0:
                return None

            return _parse_managed_objects(stdout.decode())
        except asyncio.TimeoutError:
            return None
        except Exception as e:
            logging.debug(f"BlueZ D-Bus error: {e}")
            return None

    def get_status(self) -> Dict[str, Any]:
        """Get current Bluetooth status for the API."""
        return {
            "is_playing": self.is_playing,
            "device_name": self.device_name,
            "track_info": self.track_info or None,
            "last_event_time": self.last_event_time.isoformat() if self.last_event_time else None,
        }


def _parse_managed_objects(output: str) -> Dict[str, Dict[str, Any]]:
    """Parse dbus-send GetManagedObjects output into a nested dict.

    Returns: {object_path: {interface_name: {property: value}}}

    This parser handles the verbose dbus-send text format, extracting
    object paths, interface names, and their properties (strings, variants,
    and nested dicts like Track).
    """
    objects: Dict[str, Dict[str, Any]] = {}
    lines = output.split("\n")
    i = 0

    current_path = None
    current_iface = None
    current_props: Dict[str, Any] = {}
    current_key = None
    # For parsing Track dict (nested dict inside a variant)
    in_track_dict = False
    track_dict: Dict[str, Any] = {}
    track_key = None

    while i < len(lines):
        line = lines[i].strip()

        # Object path
        if 'object path "/' in line and 'dict entry(' not in lines[max(0, i-1)].strip():
            # Save previous interface
            if current_iface and current_path is not None:
                if current_path not in objects:
                    objects[current_path] = {}
                objects[current_path][current_iface] = current_props

            start = line.find('"') + 1
            end = line.rfind('"')
            if start > 0 and end > start:
                new_path = line[start:end]
                if new_path.startswith("/org/bluez"):
                    current_path = new_path
                    current_iface = None
                    current_props = {}

        # Interface name (string key in the interface dict)
        elif 'string "org.bluez.' in line or 'string "org.freedesktop.DBus' in line:
            # Check context: this should be an interface name, not a property value
            # Interface names appear as dict keys at the top level of each object
            val_start = line.find('"') + 1
            val_end = line.rfind('"')
            if val_start > 0 and val_end > val_start:
                val = line[val_start:val_end]
                if val.startswith("org.bluez.") or val.startswith("org.freedesktop.DBus."):
                    # Save previous interface
                    if current_iface and current_path is not None:
                        if current_path not in objects:
                            objects[current_path] = {}
                        objects[current_path][current_iface] = current_props
                    current_iface = val
                    current_props = {}
                    current_key = None
                    in_track_dict = False

        # Property key (string in a dict entry under an interface)
        elif 'dict entry(' in line:
            if in_track_dict:
                track_key = None
            else:
                current_key = None

        elif current_iface and 'string "' in line:
            val_start = line.find('"') + 1
            val_end = line.rfind('"')
            if val_start > 0 and val_end > val_start:
                val = line[val_start:val_end]

                if in_track_dict:
                    if track_key is None:
                        track_key = val
                    else:
                        track_dict[track_key] = val
                        track_key = None
                elif current_key is None:
                    current_key = val
                else:
                    # String value for current property
                    current_props[current_key] = val
                    current_key = None

        elif current_key and 'uint32 ' in line:
            parts = line.split()
            for part in parts:
                try:
                    current_props[current_key] = int(part)
                    break
                except ValueError:
                    continue
            if not in_track_dict:
                current_key = None

        elif current_key and 'uint64 ' in line:
            parts = line.split()
            for part in parts:
                try:
                    current_props[current_key] = int(part)
                    break
                except ValueError:
                    continue
            if not in_track_dict:
                current_key = None

        elif current_key and 'int64 ' in line:
            parts = line.split()
            for part in parts:
                try:
                    val = int(part)
                    if in_track_dict and track_key:
                        track_dict[track_key] = val
                        track_key = None
                    else:
                        current_props[current_key] = val
                    break
                except ValueError:
                    continue
            if not in_track_dict:
                current_key = None

        elif 'boolean ' in line and current_key:
            current_props[current_key] = 'true' in line
            current_key = None

        # Detect start of Track dict (array of dict entries inside a variant)
        elif current_key == "Track" and 'array [' in line:
            in_track_dict = True
            track_dict = {}
            track_key = None

        # End of Track dict array
        elif in_track_dict and line == ']':
            in_track_dict = False
            current_props["Track"] = track_dict
            current_key = None

        i += 1

    # Save last interface
    if current_iface and current_path is not None:
        if current_path not in objects:
            objects[current_path] = {}
        objects[current_path][current_iface] = current_props

    return objects
