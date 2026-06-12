"""
Sendspin Artwork Client

A Sendspin *display* client that connects to Music Assistant and receives album
art as binary image frames over the local network. It takes CONTROLLER + METADATA
+ ARTWORK roles (NOT player — a display has no business appearing as a player in
MA's settings).

Crucial: in Sendspin, metadata + artwork are delivered *per group*. MA pushes a
client only the now-playing of the group it currently belongs to. A freshly
connected display lands in its own solo group, so MA hands it one stale/default
cover at connect and never follows the speaker's track changes (observed: the
display showed a Body Count cover while the speaker played Boards of Canada). The
CONTROLLER role fixes this: it lets the client issue `switch` commands to cycle
through the server's groups until it lands in the one that's actually PLAYING —
i.e. the speaker's group — after which MA streams it that group's cover + metadata
on every track change. The switch cycle is driven by SendspinManager's playback
watcher (see sync_to_playing_group), whether or not the Pi itself is the speaker:
the protocol only notifies a client about its *own* group, so a playing group
elsewhere can only be discovered by actively cycling — hence the periodic,
time-gated retry instead of a one-shot attempt.

This is the protocol's intended way to drive wall displays: the artwork arrives
as raw encoded images pushed by the server, so it works fully offline on the LAN
with no internet access and no external image URLs.

Runs in server-initiated mode: it advertises via mDNS (_sendspin._tcp.local.) so
Music Assistant discovers it and streams artwork to it.

The received cover is held in memory and served by FastAPI at /sendspin/artwork;
the URL is surfaced to the now-playing view via the SendspinManager broadcast path.
"""
import asyncio
import logging
import time
from typing import Awaitable, Callable, Optional

from aiosendspin.client import ClientListener, SendspinClient
from aiosendspin.models.artwork import ArtworkChannel, ClientHelloArtworkSupport
from aiosendspin.models.core import DeviceInfo
from aiosendspin.models.types import (
    ArtworkSource,
    MediaCommand,
    PictureFormat,
    PlaybackStateType,
    Roles,
)

logger = logging.getLogger(__name__)

# Distinct from the audio daemon's listener (8928) so both can advertise.
ARTWORK_LISTEN_PORT = 8930

# Negotiated max artwork resolution. Cover art is square and shown centered on
# the canvas; ~800px is sharp on 1080p without sending oversized frames.
ARTWORK_SIZE = 800

# Auto-join (CONTROLLER role) tuning. A `switch` cycles us to the next group; we
# keep switching until we land on a PLAYING group or have visited every group.
# Cap the attempts as a backstop so a server that never reports PLAYING can't
# spin us forever, and wait briefly after each switch for the group/update.
MAX_SWITCH_ATTEMPTS = 8
SWITCH_SETTLE_TIMEOUT = 2.5
# After an unsuccessful full cycle, wait this long before cycling again. MA only
# sends group/update for our own group, so playback starting in another group is
# invisible until we go looking for it — but cycling on every poll tick would
# spam switch commands.
RESYNC_INTERVAL = 30.0

_FORMAT_MIME = {
    PictureFormat.JPEG: "image/jpeg",
    PictureFormat.PNG: "image/png",
    PictureFormat.BMP: "image/bmp",
}


class SendspinArtworkClient:
    """Receives album art from Music Assistant via the Sendspin ARTWORK role."""

    def __init__(
        self,
        client_id: str,
        client_name: str,
        art_format: PictureFormat = PictureFormat.JPEG,
        art_size: int = ARTWORK_SIZE,
        on_artwork: Optional[Callable[[], Awaitable[None]]] = None,
        product_name: Optional[str] = None,
        manufacturer: Optional[str] = None,
        software_version: Optional[str] = None,
    ):
        self._client_id = client_id
        self._client_name = client_name
        self._art_format = art_format
        self._art_size = art_size
        # Device identity advertised to MA so it can label this display instead
        # of logging blank/unknown player details. All optional per the protocol.
        self._device_info = DeviceInfo(
            product_name=product_name,
            manufacturer=manufacturer,
            software_version=software_version,
        )
        # Async callback invoked (scheduled) when a new artwork frame arrives.
        self._on_artwork = on_artwork

        self._listener: Optional[ClientListener] = None
        self._client: Optional[SendspinClient] = None

        # Latest received cover art, served by the /sendspin/artwork route.
        self.art_bytes: Optional[bytes] = None
        self.art_mime: str = _FORMAT_MIME.get(art_format, "image/jpeg")
        self.art_version: int = 0
        # Absolute artwork URL from MA's METADATA role, when provided. Preferred
        # over the local binary so external screens of differing resolution can
        # fetch it directly from MA at their own size (still LAN-only).
        self.metadata_art_url: Optional[str] = None
        # Now-playing metadata from MA's METADATA role. This is the group's
        # track regardless of which device renders the audio, so it can drive
        # the display even when the Pi itself isn't the speaker.
        self.track_title: Optional[str] = None
        self.track_artist: Optional[str] = None
        self.track_album: Optional[str] = None
        self.track_duration_ms: int = 0
        # Strong refs to in-flight notify tasks so they aren't GC'd mid-await.
        self._tasks: set = set()

        # --- Group auto-join (CONTROLLER role) state ---
        # The group MA currently has us in, and whether it's actively playing.
        self._group_id: Optional[str] = None
        self._group_name: Optional[str] = None
        self._group_playing: bool = False
        # Whether MA advertised the `switch` command (controller support). If it
        # doesn't, auto-join is impossible and we say so once.
        self._switch_supported: bool = False
        self._logged_no_switch: bool = False
        # Monotonic time before which periodic callers shouldn't re-cycle after
        # a full unsuccessful switch cycle; cleared when group state changes or
        # on a fresh connection (i.e. when there's new reason to believe it'd
        # work). Playback starting in *another* group sends us no event, so the
        # cycle must still retry on a timer rather than latch off entirely.
        self._sync_backoff_until: float = 0.0
        # Signalled on every group/update so a switch can await the new state.
        self._group_changed: asyncio.Event = asyncio.Event()
        # Serialises switch cycles so concurrent poll ticks don't interleave.
        self._sync_lock: asyncio.Lock = asyncio.Lock()

    @property
    def art_url(self) -> Optional[str]:
        """Best art URL for the now-playing view.

        Prefers MA's absolute artwork URL (flexible across external screens),
        falling back to the locally-served binary frame (self-contained/offline).
        """
        if self.metadata_art_url:
            return self.metadata_art_url
        if self.art_bytes:
            return f"/sendspin/artwork?v={self.art_version}"
        return None

    @property
    def group_playing(self) -> bool:
        """True while the group MA has us in is actively playing."""
        return self._client is not None and self._group_playing

    @property
    def group_name(self) -> Optional[str]:
        """Name of the group MA currently has us in, if any."""
        return self._group_name

    def _make_client(self) -> SendspinClient:
        client = SendspinClient(
            client_id=self._client_id,
            client_name=self._client_name,
            device_info=self._device_info,
            # CONTROLLER + METADATA + ARTWORK — NO player role. CONTROLLER lets us
            # `switch` into the speaker's playing group (metadata/artwork are
            # group-scoped, so without this we'd be stuck in our own solo group
            # showing a stale cover). PLAYER is deliberately omitted: it would
            # register a muted "ghost" player in MA's settings → players page.
            roles=[Roles.CONTROLLER, Roles.METADATA, Roles.ARTWORK],
            artwork_support=ClientHelloArtworkSupport(
                channels=[
                    ArtworkChannel(
                        source=ArtworkSource.ALBUM,
                        format=self._art_format,
                        media_width=self._art_size,
                        media_height=self._art_size,
                    )
                ]
            ),
        )
        client.add_artwork_listener(self._on_artwork_frame)
        client.add_metadata_listener(self._on_metadata)
        client.add_group_update_listener(self._on_group_update)
        client.add_controller_state_listener(self._on_controller_state)
        return client

    def _on_metadata(self, payload) -> None:
        """Capture the group's now-playing metadata from MA's METADATA role.

        On a track change, drop the previous track's art first — both the URL
        and the cached binary frame — so a new track that ships no artwork_url
        doesn't keep showing the old cover. The next artwork frame for the new
        track repopulates the binary fallback.
        """
        md = getattr(payload, "metadata", None)
        if md is None:
            return

        def _str_field(name):
            # Partial updates leave fields as UndefinedField; only a real
            # string is a value (None would also mean "cleared", but partial
            # updates are common enough that we only act on real strings).
            value = getattr(md, name, None)
            return value if isinstance(value, str) else None

        # A changed title means a new track → reset stale art.
        title = _str_field("title")
        new_track = title is not None and title != self.track_title
        if new_track:
            self.track_title = title
            self.metadata_art_url = None
            # Drop the cached frame too: otherwise art_url falls back to the
            # previous track's binary cover until a new frame arrives.
            self.art_bytes = None

        artist = _str_field("artist")
        if artist is not None:
            self.track_artist = artist
        album = _str_field("album")
        if album is not None:
            self.track_album = album
        progress = getattr(md, "progress", None)
        duration = getattr(progress, "track_duration", None)
        if isinstance(duration, int):
            self.track_duration_ms = duration

        url = getattr(md, "artwork_url", None)
        # Field may be an UndefinedField/None when unset — only accept real URLs.
        if isinstance(url, str) and url.startswith(("http://", "https://")):
            if url != self.metadata_art_url:
                self.metadata_art_url = url
                logger.info("Sendspin metadata artwork_url: %s", url)
                self._notify()
        elif new_track:
            # New track with no art URL — refresh so the view drops the old cover.
            self._notify()

    def _on_artwork_frame(self, channel: int, data: bytes) -> None:
        """Store the latest artwork frame and notify the now-playing view."""
        if not data:
            return
        self.art_bytes = data
        self.art_version += 1
        logger.info(
            "Sendspin artwork received: channel=%d, %d bytes (v%d)",
            channel, len(data), self.art_version,
        )
        self._notify()

    def _on_controller_state(self, payload) -> None:
        """Track whether the server supports the `switch` command (auto-join)."""
        controller = getattr(payload, "controller", None)
        if controller is None:
            return
        commands = getattr(controller, "supported_commands", None) or []
        supported = MediaCommand.SWITCH in commands
        if supported and not self._switch_supported:
            logger.info("Sendspin controller: switch supported — group auto-join enabled")
        self._switch_supported = supported

    def _on_group_update(self, payload) -> None:
        """Record the group MA has us in and whether it's playing.

        Landing in a PLAYING group means we're with the speaker and will now
        receive its per-track artwork. Any change re-opens the switch cycle for
        periodic callers (clears the exhausted latch).
        """
        group_id = getattr(payload, "group_id", None)
        state = getattr(payload, "playback_state", None)
        playing = state == PlaybackStateType.PLAYING

        if group_id != self._group_id or playing != self._group_playing:
            self._sync_backoff_until = 0.0  # new info → worth (re)trying a switch
        self._group_id = group_id
        self._group_name = getattr(payload, "group_name", None)
        self._group_playing = playing

        logger.info(
            "Sendspin group/update: group=%s (%s) playback=%s",
            self._group_name, group_id, state.value if state else None,
        )
        self._group_changed.set()

    async def sync_to_playing_group(self) -> None:
        """Switch into the group that's actually playing (the speaker's group).

        Called periodically by SendspinManager's playback watcher. No-op while
        we're already in a playing group, when the server doesn't support
        `switch`, or within the backoff window after a full unsuccessful cycle
        (cleared early when group state changes). Cycles `switch` until a
        group/update reports PLAYING.
        """
        if self._client is None:
            return
        if self._group_playing or time.monotonic() < self._sync_backoff_until:
            return
        if not self._switch_supported:
            if not self._logged_no_switch:
                logger.warning(
                    "Sendspin: server doesn't advertise the switch command; "
                    "cannot auto-join the speaker's group for artwork"
                )
                self._logged_no_switch = True
            return

        async with self._sync_lock:
            # Re-check under the lock — a group/update may have arrived meanwhile.
            if self._client is None or self._group_playing or \
                    time.monotonic() < self._sync_backoff_until:
                return

            tried_groups: set = set()
            for attempt in range(MAX_SWITCH_ATTEMPTS):
                if self._group_playing:
                    break
                current = self._group_id
                if current is not None and current in tried_groups:
                    break  # cycled back to a group we already visited
                if current is not None:
                    tried_groups.add(current)

                self._group_changed.clear()
                try:
                    await self._client.send_group_command(MediaCommand.SWITCH)
                except Exception as e:
                    logger.warning("Sendspin switch command failed: %s", e)
                    break
                logger.info("Sendspin: sent switch (attempt %d) to find playing group", attempt + 1)
                try:
                    await asyncio.wait_for(self._group_changed.wait(), timeout=SWITCH_SETTLE_TIMEOUT)
                except asyncio.TimeoutError:
                    pass

            if self._group_playing:
                logger.info("Sendspin: joined playing group '%s'", self._group_name)
            else:
                self._sync_backoff_until = time.monotonic() + RESYNC_INTERVAL
                logger.debug(
                    "Sendspin: no playing group found after switching; retrying in %.0fs",
                    RESYNC_INTERVAL,
                )

    def _notify(self) -> None:
        """Schedule the now-playing re-broadcast when art (URL or bytes) changes."""
        if self._on_artwork is None:
            return
        try:
            task = asyncio.create_task(self._on_artwork())
            # Keep a strong reference until done so the task isn't GC'd mid-await.
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)
        except RuntimeError:
            logger.debug("No running loop to schedule artwork update")

    async def _handle_connection(self, ws) -> None:
        """Handle an incoming Music Assistant connection for its lifetime."""
        client = self._make_client()
        self._client = client
        try:
            await client.attach_websocket(ws)
        except Exception:
            logger.exception("Sendspin artwork handshake failed")
            return
        logger.info("Music Assistant connected to artwork display client")
        try:
            disconnect_event = asyncio.Event()
            unsubscribe = client.add_disconnect_listener(disconnect_event.set)
            await disconnect_event.wait()
            unsubscribe()
        finally:
            if self._client is client:
                self._client = None
            # Drop cached art/metadata so a later session never shows a previous
            # track before fresh metadata/frames arrive.
            self.metadata_art_url = None
            self.art_bytes = None
            self.track_title = None
            self.track_artist = None
            self.track_album = None
            self.track_duration_ms = 0
            # Reset group/auto-join state — a new session re-negotiates roles,
            # starts in a fresh solo group, and must re-discover switch support.
            self._group_id = None
            self._group_name = None
            self._group_playing = False
            self._switch_supported = False
            self._sync_backoff_until = 0.0
            logger.info("Music Assistant disconnected from artwork display client")

    async def start(self) -> None:
        """Start the mDNS-advertised listener so Music Assistant can connect."""
        try:
            self._listener = ClientListener(
                client_id=self._client_id,
                on_connection=self._handle_connection,
                port=ARTWORK_LISTEN_PORT,
                client_name=self._client_name,
                advertise_mdns=True,
            )
            await self._listener.start()
            logger.info(
                "Sendspin artwork client '%s' listening on :%d (mDNS advertised)",
                self._client_name, ARTWORK_LISTEN_PORT,
            )
        except Exception:
            logger.exception("Failed to start Sendspin artwork client")

    async def stop(self) -> None:
        if self._client is not None:
            try:
                await self._client.disconnect()
            except Exception:
                pass
            self._client = None
        if self._listener is not None:
            try:
                await self._listener.stop()
            except Exception:
                pass
            self._listener = None
