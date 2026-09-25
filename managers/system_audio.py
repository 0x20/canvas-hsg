"""
System audio controls: the PipeWire default sink (the one speaker volume for
every source) and systemd service checks.
"""
import re

from utils.proc import run


async def get_sink_volume() -> int:
    """Default sink volume in percent (100 when it cannot be read)."""
    _, out = await run("pactl", "get-sink-volume", "@DEFAULT_SINK@")
    match = re.search(r"(\d+)%", out)
    return int(match.group(1)) if match else 100


async def set_sink_volume(volume: int) -> bool:
    rc, _ = await run("pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{volume}%")
    return rc == 0


async def service_active(name: str) -> bool:
    _, out = await run("systemctl", "is-active", name)
    return out.strip() == "active"
