"""
Audio Conflict Manager

Handles muting/unmuting PipeWire sink-inputs to enforce "last-in wins"
audio exclusivity between Raspotify and Sendspin.

Both Raspotify (librespot) and the Sendspin daemon output audio via PipeWire.
When one starts playing, the other is muted. When the winner stops, the
previously muted source is restored.
"""
import asyncio
import logging
import re
from typing import Dict, List, Optional


# Map friendly names to PipeWire process binary names
SOURCE_BINARIES = {
    "raspotify": "librespot",
    "sendspin": "sendspin",
}


class AudioConflictManager:
    """Manages PipeWire sink-input muting for audio source exclusivity."""

    def __init__(self):
        self._muted_sources: Dict[str, List[int]] = {}

    async def mute_source(self, source_name: str) -> None:
        """Mute all PipeWire sink-inputs belonging to a source."""
        binary = SOURCE_BINARIES.get(source_name)
        if not binary:
            logging.warning(f"AudioConflict: unknown source '{source_name}'")
            return

        indices = await self._find_sink_inputs(binary)
        if not indices:
            logging.debug(f"AudioConflict: no sink-inputs found for {source_name} ({binary})")
            return

        muted = []
        for idx in indices:
            success = await self._set_mute(idx, mute=True)
            if success:
                muted.append(idx)

        if muted:
            self._muted_sources[source_name] = muted
            logging.info(f"AudioConflict: muted {source_name} (sink-inputs: {muted})")

    async def unmute_source(self, source_name: str) -> None:
        """Unmute previously muted sink-inputs for a source."""
        indices = self._muted_sources.pop(source_name, [])
        if not indices:
            return

        for idx in indices:
            await self._set_mute(idx, mute=False)

        logging.info(f"AudioConflict: unmuted {source_name} (sink-inputs: {indices})")

    async def unmute_all(self) -> None:
        """Unmute everything (cleanup on shutdown)."""
        for source_name in list(self._muted_sources.keys()):
            await self.unmute_source(source_name)

    async def _find_sink_inputs(self, binary_name: str) -> List[int]:
        """Find PipeWire sink-input indices by application binary name."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "pactl", "list", "sink-inputs",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
            output = stdout.decode()
        except Exception as e:
            logging.warning(f"AudioConflict: failed to list sink-inputs: {e}")
            return []

        # Parse pactl output: blocks start with "Sink Input #<index>"
        # and contain "application.process.binary = "<name>""
        indices = []
        current_index: Optional[int] = None
        for line in output.splitlines():
            idx_match = re.match(r"Sink Input #(\d+)", line)
            if idx_match:
                current_index = int(idx_match.group(1))
            if current_index is not None and "application.process.binary" in line:
                if binary_name in line:
                    indices.append(current_index)
                    current_index = None
        return indices

    async def _set_mute(self, sink_input_index: int, mute: bool) -> bool:
        """Mute or unmute a specific sink-input."""
        mute_val = "1" if mute else "0"
        try:
            proc = await asyncio.create_subprocess_exec(
                "pactl", "set-sink-input-mute", str(sink_input_index), mute_val,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(proc.communicate(), timeout=5)
            return proc.returncode == 0
        except Exception as e:
            logging.warning(f"AudioConflict: failed to set mute on sink-input {sink_input_index}: {e}")
            return False
