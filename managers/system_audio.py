"""
System audio controls: the PipeWire default sink and the Raspotify ALSA mixer.
"""
import re
from typing import Optional

from utils.proc import run

# ALSA card and control that Raspotify plays through
SPOTIFY_MIXER_CARD = "3"
SPOTIFY_MIXER_CONTROL = "PCM"


async def get_sink_volume() -> int:
    """Default sink volume in percent (100 when it cannot be read)."""
    _, out = await run("pactl", "get-sink-volume", "@DEFAULT_SINK@")
    match = re.search(r"(\d+)%", out)
    return int(match.group(1)) if match else 100


async def set_sink_volume(volume: int) -> bool:
    rc, _ = await run("pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{volume}%")
    return rc == 0


async def get_spotify_volume() -> Optional[int]:
    _, out = await run("amixer", "-c", SPOTIFY_MIXER_CARD, "get", SPOTIFY_MIXER_CONTROL)
    match = re.search(r"\[(\d+)%\]", out)
    return int(match.group(1)) if match else None


async def set_spotify_volume(volume: int) -> bool:
    rc, _ = await run("amixer", "-c", SPOTIFY_MIXER_CARD, "set", SPOTIFY_MIXER_CONTROL, f"{volume}%")
    return rc == 0


async def service_active(name: str) -> bool:
    _, out = await run("systemctl", "is-active", name)
    return out.strip() == "active"
