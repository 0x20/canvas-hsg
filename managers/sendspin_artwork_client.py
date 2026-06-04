"""
Sendspin Artwork Client

A Sendspin *display* client (ARTWORK + METADATA roles) that connects to Music
Assistant and receives album art as binary image frames over the local network.
This is the protocol's intended way to drive wall displays: the artwork arrives
as raw encoded images pushed by the server, so it works fully offline on the LAN
with no internet access and no external image URLs.

Runs in server-initiated mode: it advertises via mDNS (_sendspin._tcp.local.) so
Music Assistant discovers it and streams artwork to it. Group this display with
the audio speaker in Music Assistant so MA pushes it the now-playing artwork.

The received cover is held in memory and served by FastAPI at /sendspin/artwork;
the URL is surfaced to the now-playing view via the SendspinManager broadcast path.
"""
import asyncio
import logging
from typing import Awaitable, Callable, Optional

from aiosendspin.client import ClientListener, SendspinClient
from aiosendspin.models.artwork import ArtworkChannel, ClientHelloArtworkSupport
from aiosendspin.models.types import ArtworkSource, PictureFormat, Roles

logger = logging.getLogger(__name__)

# Distinct from the audio daemon's listener (8928) so both can advertise.
ARTWORK_LISTEN_PORT = 8930

# Negotiated max artwork resolution. Cover art is square and shown centered on
# the canvas; ~800px is sharp on 1080p without sending oversized frames.
ARTWORK_SIZE = 800

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
    ):
        self._client_id = client_id
        self._client_name = client_name
        self._art_format = art_format
        self._art_size = art_size
        # Async callback invoked (scheduled) when a new artwork frame arrives.
        self._on_artwork = on_artwork

        self._listener: Optional[ClientListener] = None
        self._client: Optional[SendspinClient] = None

        # Latest received cover art, served by the /sendspin/artwork route.
        self.art_bytes: Optional[bytes] = None
        self.art_mime: str = _FORMAT_MIME.get(art_format, "image/jpeg")
        self.art_version: int = 0

    @property
    def art_url(self) -> Optional[str]:
        """Absolute-path URL for the current cover (cache-busted), or None."""
        if not self.art_bytes:
            return None
        return f"/sendspin/artwork?v={self.art_version}"

    def _make_client(self) -> SendspinClient:
        client = SendspinClient(
            client_id=self._client_id,
            client_name=self._client_name,
            roles=[Roles.METADATA, Roles.ARTWORK],
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
        return client

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
        if self._on_artwork is not None:
            try:
                asyncio.create_task(self._on_artwork())
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
