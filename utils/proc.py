"""Non-blocking subprocess helper for async code."""
import asyncio
import logging
from typing import Tuple


async def run(*cmd: str, timeout: float = 5) -> Tuple[int, str]:
    """Run a command without blocking the event loop.

    Returns (returncode, stdout). A missing binary, a timeout or any other
    failure returns (-1, "") and logs a warning.
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except Exception as e:
        logging.warning(f"{cmd[0]} failed to start: {e}")
        return -1, ""
    try:
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        logging.warning(f"{' '.join(cmd)} timed out after {timeout}s")
        return -1, ""
    return proc.returncode, stdout.decode(errors="replace")
