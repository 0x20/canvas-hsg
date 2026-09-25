"""
Audio Conflict Manager

The single owner of audio exclusivity ("last-in wins").

Sources:
  stream    - browser <audio> radio/clip (AudioManager)
  video     - unmuted YouTube/Twitch in the kiosk (PlaybackManager)
  spotify   - Raspotify/librespot, silenced by muting its PipeWire sink-inputs
  sendspin  - Sendspin daemon, silenced by muting its PipeWire sink-inputs
  bluetooth - A2DP sink, silenced by an AVRCP pause

A source that starts calls claim(); every other source is stopped, paused or
muted. When it stops it calls release(), which unmutes only the sinks that
this source muted. A sink muted by a later claimant stays muted.
"""
import logging
import re
from typing import Dict, List, Optional

from utils.proc import run


# Map friendly names to PipeWire process binary names
SOURCE_BINARIES = {
    "raspotify": "librespot",
    "sendspin": "sendspin",
}

# Claimant name -> the PipeWire sink it owns
OWNER_SINKS = {
    "spotify": "raspotify",
    "sendspin": "sendspin",
}

SOURCES = ("stream", "video", "spotify", "sendspin", "bluetooth")


class AudioConflictManager:
    """Enforces one audible source at a time across all audio managers."""

    def __init__(self):
        # sink name -> muted sink-input indices
        self._muted_sources: Dict[str, List[int]] = {}
        # sink name -> claimant that muted it
        self._mute_owner: Dict[str, str] = {}
        # Wired in main.py after construction
        self.audio_manager = None
        self.playback_manager = None
        self.spotify_manager = None
        self.sendspin_manager = None
        self.bluetooth_manager = None

    def is_muted(self, sink: str) -> bool:
        return sink in self._mute_owner

    async def claim(self, owner: str) -> None:
        """Make `owner` the only audible source."""
        if owner not in SOURCES:
            raise ValueError(f"unknown audio source '{owner}'")
        logging.info(f"AudioConflict: {owner} claims audio")

        # Take over the sinks that are already muted first. The stops below
        # call release() of the old owner, which must not unmute them.
        own_sink = OWNER_SINKS.get(owner)
        for sink in self._mute_owner:
            if sink != own_sink:
                self._mute_owner[sink] = owner

        if owner != "stream" and self.audio_manager:
            await self.audio_manager.stop_audio_stream()
        if owner != "video" and self.playback_manager:
            await self.playback_manager.stop_playback()
        if owner != "bluetooth" and self.bluetooth_manager:
            await self.bluetooth_manager.pause_playback()
        if owner != "spotify" and self.spotify_manager:
            self.spotify_manager.on_preempted()
        if owner != "sendspin" and self.sendspin_manager:
            self.sendspin_manager.on_preempted()

        for claimant, sink in OWNER_SINKS.items():
            if claimant == owner:
                await self._unmute(sink)
            else:
                await self.mute_source(sink, owner)

    async def release(self, owner: str) -> None:
        """`owner` stopped: unmute the sinks it muted."""
        for sink, sink_owner in list(self._mute_owner.items()):
            if sink_owner == owner:
                await self._unmute(sink)
                if sink == "raspotify" and self.spotify_manager:
                    await self.spotify_manager.on_unmuted()
                if sink == "sendspin" and self.sendspin_manager:
                    self.sendspin_manager.on_unmuted()

    async def reassert(self, owner: str) -> None:
        """Mute new sink-inputs of the sinks that `owner` holds muted."""
        for sink, sink_owner in list(self._mute_owner.items()):
            if sink_owner == owner:
                await self.mute_source(sink, owner)

    async def mute_source(self, sink: str, owner: str) -> None:
        """Mute all PipeWire sink-inputs of `sink` on behalf of `owner`.

        Safe to call again: sink-inputs that appeared since the last call are
        muted too (librespot opens a new one per track).
        """
        binary = SOURCE_BINARIES.get(sink)
        if not binary:
            logging.warning(f"AudioConflict: unknown sink '{sink}'")
            return

        self._mute_owner[sink] = owner
        indices = await self._find_sink_inputs(binary)
        known = self._muted_sources.setdefault(sink, [])
        for idx in indices:
            if idx not in known and await self._set_mute(idx, mute=True):
                known.append(idx)
                logging.info(f"AudioConflict: muted {sink} sink-input {idx} for {owner}")

    async def _unmute(self, sink: str) -> None:
        self._mute_owner.pop(sink, None)
        indices = self._muted_sources.pop(sink, [])
        for idx in indices:
            await self._set_mute(idx, mute=False)
        if indices:
            logging.info(f"AudioConflict: unmuted {sink} (sink-inputs: {indices})")

    async def unmute_all(self) -> None:
        """Unmute everything (cleanup on shutdown)."""
        for sink in list(self._mute_owner):
            await self._unmute(sink)

    async def _find_sink_inputs(self, binary_name: str) -> List[int]:
        """Find PipeWire sink-input indices by application binary name."""
        rc, output = await run("pactl", "list", "sink-inputs")
        if rc != 0:
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
        rc, _ = await run("pactl", "set-sink-input-mute", str(sink_input_index), "1" if mute else "0")
        return rc == 0
