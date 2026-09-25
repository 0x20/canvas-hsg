"""
Device names: what phones and Music Assistant see when they look for the canvas.

- Spotify Connect: raspotify's LIBRESPOT_NAME
- Bluetooth: the BlueZ adapter alias
- Music Assistant: the sendspin daemon's --name (and the art client "<name> - art")

Spotify and Music Assistant names go to state/names.env, which the systemd
units read, followed by a service restart. See setup.sh.
"""
import logging
from typing import Dict, Optional

from config import DEVICE_NAME, SENDSPIN_NAME
from utils.names_env import read_names, valid_name, write_name
from utils.proc import run

NAME_KINDS = ("spotify", "bluetooth", "music_assistant")


class DeviceNamesManager:
    def __init__(self, bluetooth_manager=None, artwork_client=None):
        self.bluetooth_manager = bluetooth_manager
        self.artwork_client = artwork_client

    def get(self) -> Dict[str, Optional[str]]:
        names = read_names()
        return {
            "spotify": names.get("LIBRESPOT_NAME", DEVICE_NAME),
            "bluetooth": self.bluetooth_manager.adapter_name if self.bluetooth_manager else None,
            "music_assistant": names.get("SENDSPIN_NAME", SENDSPIN_NAME),
        }

    async def set(self, kind: str, name: str) -> None:
        """Rename one device. Raises ValueError for a bad name, RuntimeError on failure."""
        name = name.strip()
        if kind not in NAME_KINDS:
            raise ValueError(f"Unknown name kind '{kind}'")
        if not valid_name(name):
            raise ValueError("A name has 1-40 characters, without quotes, backslashes or $")

        if kind == "bluetooth":
            if not self.bluetooth_manager or not await self.bluetooth_manager.set_adapter_name(name):
                raise RuntimeError("bluetoothctl could not set the name")
        elif kind == "spotify":
            write_name("LIBRESPOT_NAME", name)
            await self._restart("raspotify")
        else:
            write_name("SENDSPIN_NAME", name)
            await self._restart("sendspin")
            if self.artwork_client:
                await self.artwork_client.rename(f"{name} - art")
        logging.info(f"Device name for {kind} set to '{name}'")

    @staticmethod
    async def _restart(service: str) -> None:
        # -n: fail at once if the sudoers rule from setup.sh is missing
        rc, _ = await run("sudo", "-n", "systemctl", "restart", service, timeout=20)
        if rc != 0:
            raise RuntimeError(f"Could not restart {service}; run setup.sh to install the sudoers rule")
