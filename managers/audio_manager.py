"""
Audio Manager

Handles audio streaming via browser <audio> element controlled by WebSocket.
Replaces MPV audio pool with WebSocket commands to the React AudioPlayer component.
"""
import asyncio
import ipaddress
import logging
import os
import re
import time
import aiohttp
from datetime import datetime
from typing import Optional, Dict, Any
from urllib.parse import urlparse

from config import METADATA_UPDATE_INTERVAL


# Radio France livemeta IDs of the FIP streams, by the part after "fip" in the
# stream URL (icecast.radiofrance.fr/fip<name>-midfi.mp3)
FIP_STATION_IDS = {
    "": 7, "rock": 64, "jazz": 65, "groove": 66, "world": 69, "nouveautes": 70,
    "reggae": 71, "electro": 74, "metal": 77, "pop": 78,
}


class AudioManager:
    """Manages audio streaming via browser WebSocket"""

    def __init__(self, audio_ws_manager, audio_conflict=None):
        self.audio_ws_manager = audio_ws_manager
        self.audio_conflict = audio_conflict
        # Read only, for the combined status report
        self.playback_manager = None
        self.spotify_manager = None
        self.sendspin_manager = None
        self.bluetooth_manager = None
        # Display stack — used to show fullscreen station art for audio streams.
        self.display_stack = None
        # Spotify-events WebSocketManager — drives the canvas now-playing card
        # with live stream metadata (set in main.py, same instance Spotify uses).
        self.now_playing_ws = None
        # Resolved station logo for the current stream (reused as the card's
        # "album art"); plus bookkeeping so we only push the card / re-broadcast
        # when the track actually changes.
        self._current_art_url: Optional[str] = None
        self._radio_card_active: bool = False
        self._last_published_key: Optional[tuple] = None
        # Cached SomaFM id→logo map (channels.json); extensions vary per station.
        self._somafm_logos: Dict[str, str] = {}
        self._somafm_logos_ts: float = 0.0
        # StationStore with the preset stations (set in main.py)
        self.stations = None
        # Station names announced by streams via their icy-name header.
        self._icy_names: Dict[str, str] = {}
        # StationArtCache — resolves and stores station logos on disk (set in
        # main.py). Without it we fall back to remote seed URLs.
        self.station_art = None

        # Shared HTTP session for playlist, metadata and logo requests
        self._session: Optional[aiohttp.ClientSession] = None

        # Current audio state
        self.current_audio_stream: Optional[str] = None
        # The URL the browser actually plays (playlists resolved)
        self.current_resolved_url: Optional[str] = None
        self.audio_volume: int = 80
        self._is_playing: bool = False

        # Cached status from browser reports
        self._browser_status: Dict[str, Any] = {}

        # Metadata
        self.current_metadata: Dict[str, Any] = {}
        self.metadata_task: Optional[asyncio.Task] = None
        self._art_task: Optional[asyncio.Task] = None

    def _http(self) -> aiohttp.ClientSession:
        """Shared HTTP session, created on first use (needs the running loop)."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(headers={"User-Agent": "HSGCanvas/4.0"})
        return self._session

    async def cleanup(self):
        """Stop the stream and close the HTTP session."""
        await self.stop_audio_stream()
        if self._session and not self._session.closed:
            await self._session.close()

    async def _resolve_audio_url(self, stream_url: str) -> str:
        """Resolve PLS/M3U playlist URLs to direct stream URLs"""
        is_pls = stream_url.endswith('.pls')
        is_m3u = stream_url.endswith('.m3u')  # not .m3u8: HLS is handled by the browser
        if not (is_pls or is_m3u):
            return stream_url
        try:
            async with self._http().get(stream_url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status != 200:
                    return stream_url
                content = await response.text()
            for line in content.split('\n'):
                line = line.strip()
                if is_pls and line.startswith('File1='):
                    direct_url = line.split('=', 1)[1].strip()
                elif is_m3u and line and not line.startswith('#'):
                    direct_url = line
                else:
                    continue
                logging.info(f"Resolved playlist {stream_url} to {direct_url}")
                return direct_url
        except Exception as e:
            logging.warning(f"Failed to resolve playlist URL {stream_url}: {e}")
        return stream_url

    async def start_audio_stream(self, stream_url: str, volume: Optional[int] = None) -> bool:
        """Start audio streaming via browser WebSocket"""
        try:
            # Stop, pause or mute every other audio source
            if self.audio_conflict:
                await self.audio_conflict.claim("stream")

            # Replace the current stream. No release: this source keeps the audio.
            await self._teardown()

            # Use provided volume or current setting
            if volume is not None:
                self.audio_volume = max(0, min(100, volume))

            # Resolve playlist URLs to direct stream URLs
            resolved_url = await self._resolve_audio_url(stream_url)

            logging.info(f"Starting audio stream via browser: {resolved_url} (original: {stream_url}) at volume {self.audio_volume}")

            self.current_audio_stream = stream_url
            self.current_resolved_url = resolved_url
            self._is_playing = True
            await self.audio_ws_manager.broadcast_raw(self.play_command())

            # Show the now-playing card right away, seeded with the station
            # name. The metadata loop fills in the live track title/artist once
            # it polls. Local sound-effect clips (Pi-served *.mp3) get no card —
            # they accompany an image the automation pushes separately.
            await self._publish_card()
            self.start_metadata_updates()

            # A station logo (curated / SomaFM / looked up) doubles as the card
            # art. A first lookup can take many seconds, so it runs after the
            # reply; without one the React view shows a generic radio backdrop.
            self._art_task = asyncio.create_task(self._load_station_art(stream_url))
            return True

        except Exception as e:
            logging.error(f"Failed to start audio stream {stream_url}: {e}")
            return False

    async def _load_station_art(self, stream_url: str):
        art = await self._resolve_station_art(stream_url)
        if art and self.current_audio_stream == stream_url:
            self._current_art_url = art
            await self._publish_card()

    def play_command(self) -> Optional[Dict[str, Any]]:
        """The audio_play command for the current stream, or None.

        Also sent to a browser that (re)connects, so it gets the resolved URL:
        a browser cannot play a .pls or .m3u playlist.
        """
        if not self.current_audio_stream:
            return None
        return {
            "type": "audio_play",
            "url": self.current_resolved_url or self.current_audio_stream,
            "volume": self.audio_volume,
        }

    async def stop_audio_stream(self) -> bool:
        """Stop the current audio stream via WebSocket"""
        try:
            if self.current_audio_stream or self._is_playing:
                logging.info("Stopping audio stream")
                await self.audio_ws_manager.broadcast_raw({"type": "audio_stop"})
                await self._teardown()
                logging.info("Audio stream stopped")
            if self.audio_conflict:
                await self.audio_conflict.release("stream")
            return True
        except Exception as e:
            logging.error(f"Failed to stop audio stream: {e}")
            self.current_audio_stream = None
            self._is_playing = False
            return False

    async def _teardown(self):
        """Clear the stream state, the metadata loop and the canvas card."""
        self.current_audio_stream = None
        self.current_resolved_url = None
        self._is_playing = False
        self.stop_metadata_updates()
        if self._art_task:
            self._art_task.cancel()
            self._art_task = None
        if self.display_stack:
            await self.display_stack.remove("audio-art")
            await self.display_stack.remove("radio")
        self._radio_card_active = False
        self._last_published_key = None
        self._current_art_url = None

    async def set_volume(self, volume: int) -> bool:
        """Set audio volume (0-100)"""
        try:
            self.audio_volume = max(0, min(100, volume))

            await self.audio_ws_manager.broadcast_raw({
                "type": "audio_volume",
                "volume": self.audio_volume,
            })

            logging.info(f"Set audio volume to {self.audio_volume}")
            return True
        except Exception as e:
            logging.error(f"Failed to set volume: {e}")
            return False

    async def toggle_pause(self) -> bool:
        """Toggle audio pause/play"""
        try:
            await self.audio_ws_manager.broadcast_raw({
                "type": "audio_pause",
            })
            return True
        except Exception as e:
            logging.error(f"Failed to toggle pause: {e}")
            return False

    def handle_browser_status(self, status: Dict[str, Any]):
        """Handle status update from browser AudioPlayer component"""
        self._browser_status = status
        self._is_playing = status.get("playing", False)

    async def handle_browser_ended(self, src: str = ""):
        """Browser reports a finite clip finished playing on its own.

        Fire-and-forget clips (e.g. sound effects started via HA without a
        following stop) would otherwise leave the fullscreen station-art
        overlay stuck forever. Clear playback state and drop the overlay.
        """
        # A late report for a clip that was already replaced must not stop the
        # new stream. The browser reports an absolute URL.
        current = self.current_resolved_url
        if not current or (src and src != current and not src.endswith(current)):
            logging.info(f"Ignoring ended report for a stale clip: {src}")
            return
        logging.info(f"Audio clip ended in browser: {src or '(unknown src)'}")
        await self._teardown()
        if self.audio_conflict:
            await self.audio_conflict.release("stream")

    def get_audio_status(self) -> Dict[str, Any]:
        """Get current audio streaming status across all sources"""
        # Collect all active sources
        sources = [
            ("audio_stream", lambda: self._is_playing and self.current_audio_stream),
            ("spotify", lambda: self.spotify_manager and self.spotify_manager.is_playing),
            ("sendspin", lambda: self.sendspin_manager and self.sendspin_manager.is_playing),
            ("bluetooth", lambda: self.bluetooth_manager and self.bluetooth_manager.is_playing),
            ("youtube", lambda: self.playback_manager and self.playback_manager.is_playing),
        ]
        active_sources = [name for name, check in sources if check()]

        status = {
            "is_playing": bool(active_sources),
            "sources": active_sources,
            "volume": self.audio_volume,
        }

        if "audio_stream" in active_sources:
            status["current_stream"] = self.current_audio_stream
            status["stream_name"] = self._get_friendly_stream_name(self.current_audio_stream)
            if self.current_metadata:
                status["metadata"] = self.current_metadata

        return status

    def _get_friendly_stream_name(self, stream_url: str) -> str:
        """Convert stream URL to a user-friendly name"""
        if not stream_url:
            return "Unknown Stream"

        # A configured preset knows its own name ("Studio Brussel"), which beats
        # every guess below — the host-based fallback yields eyesores like
        # "Stream from icecast.vrtcdn.be" on the canvas.
        preset = self._preset(stream_url).get("name")
        if preset:
            return preset

        # Station name announced by the stream itself, when it sends one.
        icy_name = self._icy_names.get(stream_url)
        if icy_name:
            return icy_name

        if "soma.fm" in stream_url.lower() or "somafm" in stream_url.lower():
            parts = stream_url.split('/')
            for part in parts:
                if part and not part.startswith('http') and '.' not in part:
                    return f"SomaFM - {part.title()}"
            return "SomaFM"
        elif "radio" in stream_url.lower():
            return "Radio Stream"
        elif stream_url.startswith("http"):
            try:
                parsed = urlparse(stream_url)
                hostname = parsed.hostname or "Unknown"
                return f"Stream from {hostname}"
            except:
                return "Audio Stream"
        else:
            return "Audio Stream"

    async def _fetch_icy_metadata(self, stream_url: str) -> Optional[Dict[str, Any]]:
        """Live track info from the stream's own ICY metadata, if it sends any.

        Shoutcast/Icecast interleave a metadata block into the audio every
        `icy-metaint` bytes, holding `StreamTitle='Artist - Title'`. That works
        for any station regardless of whether it has a JSON API, so it's the
        general fallback behind SomaFM's richer feed. Stations that only
        announce themselves (VRT sends `StreamTitle='VRT Studio Brussel'`) yield
        no track, which we detect by comparing against the station name.
        """
        try:
            timeout = aiohttp.ClientTimeout(total=15)
            headers = {"Icy-MetaData": "1"}
            async with self._http().get(stream_url, timeout=timeout, headers=headers) as resp:
                if resp.status not in (200, 206):
                    return None

                icy_name = (resp.headers.get("icy-name") or "").strip()
                if icy_name:
                    self._icy_names[stream_url] = icy_name

                try:
                    interval = int(resp.headers.get("icy-metaint", 0))
                except ValueError:
                    interval = 0
                if interval <= 0:
                    return None

                # Skip one audio block, then read the length-prefixed
                # metadata block that follows it.
                await resp.content.readexactly(interval)
                length = (await resp.content.readexactly(1))[0] * 16
                if length <= 0:
                    return None
                block = await resp.content.readexactly(length)
        except Exception as e:
            logging.debug(f"ICY metadata read failed for {stream_url}: {e}")
            return None

        match = re.search(r"StreamTitle='(.*?)';", block.decode("utf-8", "ignore"))
        if not match:
            return None
        title = match.group(1).strip()
        station = self._get_friendly_stream_name(stream_url)
        if not title:
            return None

        # Many stations park their own name in StreamTitle when they broadcast
        # no track info at all — VRT sends "VRT Studio Brussel" forever. That's
        # not a track, so leave the plain station card up. Compare loosely: the
        # announced name rarely matches our preset name character for character.
        def norm(s: str) -> str:
            return re.sub(r"[^a-z0-9]", "", s.lower())

        norm_title = norm(title)
        for other in (station, self._icy_names.get(stream_url, "")):
            norm_other = norm(other)
            if norm_other and (norm_title in norm_other or norm_other in norm_title):
                return None

        artist = ""
        if " - " in title:
            artist, title = (p.strip() for p in title.split(" - ", 1))
        return {"title": title, "artist": artist, "station": station, "source": "icy"}

    def _preset(self, stream_url: str) -> Dict[str, Any]:
        """The station list entry for this URL (name, image), or {}."""
        return (self.stations.by_url(stream_url) if self.stations else None) or {}

    async def warm_station_art(self, delay: float = 1.0):
        """Look up the logo of every preset station that has none cached yet.

        Runs in the background, one station at a time, so the control panel
        can show logos before anyone plays a station. Stations without a
        usable image are cached as misses and retried after a day.
        """
        if not self.stations or not self.station_art:
            return
        urls = [s["url"] for s in self.stations.stations()]
        found = 0
        for url in urls:
            try:
                if await self._resolve_station_art(url):
                    found += 1
            except Exception as e:
                logging.warning(f"Station art warm-up failed for {url}: {e}")
            await asyncio.sleep(delay)
        logging.info(f"Station art: {found} of {len(urls)} preset stations have a logo")

    async def _somafm_logo(self, seg: str) -> str:
        """Exact SomaFM cover URL for a station, given the stream basename.

        Logo file extensions vary per station (e.g. thetrip is .jpg), so use the
        API's id→xlimage map rather than guessing. Tries the basename as-is
        (handles ids ending in digits, e.g. sf1033) then with a trailing bitrate
        suffix removed (groovesalad256 → groovesalad). The channels list is
        cached for a day, with a derived 512px PNG fallback.
        """
        stripped = seg.rstrip("0123456789") or seg
        if not self._somafm_logos or (time.time() - self._somafm_logos_ts) > 86400:
            try:
                async with self._http().get(
                    "https://api.somafm.com/channels.json",
                    timeout=aiohttp.ClientTimeout(total=8),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        self._somafm_logos = {
                            c["id"]: (c.get("xlimage") or c.get("largeimage") or c.get("image"))
                            for c in data.get("channels", []) if c.get("id")
                        }
                        self._somafm_logos_ts = time.time()
            except Exception as e:
                logging.debug(f"SomaFM channels.json fetch failed: {e}")
        return (
            self._somafm_logos.get(seg)
            or self._somafm_logos.get(stripped)
            or f"https://api.somafm.com/logos/512/{stripped}512.png"
        )

    async def _resolve_station_art(self, stream_url: str) -> Optional[str]:
        """Best fullscreen station-logo URL for an audio stream, or None.

        The two sources we can derive directly — a curated `image:` in the
        station list and SomaFM's own cover API — become *seeds* for the
        station-art cache, which also searches the open station database and the
        station's homepage. The cache returns a local /station-art/ URL, so the
        canvas renders art the Pi already holds.

        Falls back to the seed's remote URL if the cache can't store anything,
        and finally to None, which lets the canvas show the station name on a
        generic radio backdrop. We deliberately never fall back to a favicon
        service: for bare CDN hosts it just returns a generic globe icon.
        """
        if not stream_url:
            return None

        host = (urlparse(stream_url).hostname or "").lower()
        if not host or self._is_local_host(host):
            return None

        seeds = []
        curated = self._preset(stream_url).get("image")
        if curated:
            seeds.append(curated)

        # SomaFM: exact cover from the API, keyed by station id (the stream
        # basename; bitrate suffixes are handled inside _somafm_logo).
        if "somafm" in host or "soma.fm" in host:
            seg = os.path.splitext(os.path.basename(urlparse(stream_url).path))[0]
            if seg:
                seeds.append(await self._somafm_logo(seg))

        if self.station_art:
            try:
                local = await self.station_art.resolve(
                    stream_url,
                    station_name=self._preset(stream_url).get("name"),
                    seed_candidates=seeds,
                    preferred=curated,
                )
                if local:
                    return local
            except Exception as e:
                logging.warning(f"Station art lookup failed for {stream_url}: {e}")

        return seeds[0] if seeds else None

    @staticmethod
    def _is_local_host(host: str) -> bool:
        """True for loopback / private / non-routable hosts that have no real favicon."""
        if host in ("localhost",) or host.endswith((".local", ".lan", ".localhost")):
            return True
        try:
            ip = ipaddress.ip_address(host)
            return ip.is_loopback or ip.is_private or ip.is_link_local
        except ValueError:
            return False

    def _detect_stream_type(self, stream_url: str) -> Optional[Dict[str, Any]]:
        """Detect the type of audio stream for metadata fetching"""
        if not stream_url:
            return None

        # Stations whose stream carries no track title, but whose own API does.
        # Checked before the generic icecast rule: these hosts contain "icecast".
        lower = stream_url.lower()
        fip = re.search(r"icecast\.radiofrance\.fr/fip([a-z]*)-", lower)
        if fip and fip.group(1) in FIP_STATION_IDS:
            return {"type": "fip", "id": FIP_STATION_IDS[fip.group(1)]}
        if "kexp" in lower:
            return {"type": "kexp"}
        bbc = re.search(r"(bbc_[a-z0-9_]+)\.m3u8", lower)
        if bbc:
            return {"type": "bbc", "service": bbc.group(1)}
        if lower.endswith("/willy.mp3") and "qmusicbe" in lower:
            return {"type": "willy"}

        if "soma.fm" in stream_url.lower() or "somafm" in stream_url.lower():
            # Station id = stream basename without extension (e.g.
            # spacestation.pls → "spacestation"), the same derivation
            # _resolve_station_art uses for the logo, so the name and the cover
            # always refer to the same station. (The old per-segment scan
            # skipped any segment containing a ".", so every *.pls URL fell
            # through to a hardcoded "groovesalad" default.)
            seg = os.path.splitext(os.path.basename(urlparse(stream_url).path))[0].lower()
            return {"type": "somafm", "station": seg or "groovesalad"}

        if "radioparadise.com" in stream_url.lower():
            if "mellow" in stream_url.lower():
                channel = 1
            elif "rock" in stream_url.lower():
                channel = 2
            elif "global" in stream_url.lower():
                channel = 3
            else:
                channel = 0
            return {"type": "radioparadise", "channel": channel}

        if "icecast" in stream_url.lower() or ":8000" in stream_url:
            try:
                parsed = urlparse(stream_url)
                server = f"{parsed.scheme}://{parsed.netloc}"
                return {"type": "icecast", "server": server}
            except:
                pass

        return None

    async def _get_json(self, url: str) -> Optional[Any]:
        """GET a JSON document; None on any failure."""
        try:
            async with self._http().get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    return await resp.json(content_type=None)
        except Exception as e:
            logging.warning(f"Failed to fetch metadata from {url}: {e}")
        return None

    async def _fetch_metadata(self, stream_info: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Fetch metadata from appropriate API"""
        if stream_info['type'] == 'somafm':
            data = await self._get_json(f"https://somafm.com/songs/{stream_info['station']}.json")
            if data and data.get('songs'):
                current = data['songs'][0]
                return {
                    'title': current.get('title', 'Unknown Track'),
                    'artist': current.get('artist', ''),
                    'album': current.get('album', ''),
                    'station': f"SomaFM {stream_info['station'].title()}",
                    'source': 'somafm'
                }

        elif stream_info['type'] == 'radioparadise':
            data = await self._get_json(
                f"https://api.radioparadise.com/api/now_playing?chan={stream_info['channel']}")
            if data:
                channel_names = ['Main Mix', 'Mellow Mix', 'Rock Mix', 'Global Mix']
                return {
                    'title': data.get('title', 'Unknown Track'),
                    'artist': data.get('artist', ''),
                    'album': data.get('album', '') + (f" ({data.get('year')})" if data.get('year') else ''),
                    'station': f"Radio Paradise {channel_names[stream_info['channel']]}",
                    'source': 'radioparadise'
                }

        elif stream_info['type'] == 'fip':
            data = await self._get_json(f"https://api.radiofrance.fr/livemeta/live/{stream_info['id']}/fip_extended")
            now = (data or {}).get('now') or {}
            # Between songs "now" is the presenter ("Le direct") without interpreters
            if now.get('title') and now.get('interpreters'):
                return {'title': now['title'], 'artist': now['interpreters'],
                        'album': now.get('album') or '', 'station': 'FIP', 'source': 'fip'}

        elif stream_info['type'] == 'kexp':
            data = await self._get_json("https://api.kexp.org/v2/plays/?limit=1")
            play = ((data or {}).get('results') or [{}])[0]
            # An "airbreak" is the DJ talking: no track
            if play.get('play_type') == 'trackplay' and play.get('song'):
                return {'title': play['song'], 'artist': play.get('artist') or '',
                        'album': play.get('album') or '', 'station': 'KEXP', 'source': 'kexp'}

        elif stream_info['type'] == 'bbc':
            data = await self._get_json(
                f"https://rms.api.bbc.co.uk/v2/services/{stream_info['service']}/segments/latest")
            for segment in (data or {}).get('data') or []:
                if (segment.get('offset') or {}).get('now_playing'):
                    titles = segment.get('titles') or {}
                    return {'title': titles.get('secondary') or '', 'artist': titles.get('primary') or '',
                            'album': '', 'station': 'BBC', 'source': 'bbc'}

        elif stream_info['type'] == 'willy':
            data = await self._get_json("https://api.willy.radio/2.4/tracks/plays?limit=1")
            track = ((data or {}).get('played_tracks') or [{}])[0]
            try:
                ends = datetime.fromisoformat(track['played_at']).timestamp() + track.get('duration', 0)
            except (KeyError, TypeError, ValueError):
                ends = 0
            # The feed lists the last track; after it ends, the DJ or an ad is on
            if track.get('title') and ends + 30 > time.time():
                return {'title': track['title'], 'artist': (track.get('artist') or {}).get('name', ''),
                        'album': '', 'station': 'Willy', 'source': 'willy'}

        elif stream_info['type'] == 'icecast':
            data = await self._get_json(f"{stream_info['server']}/status-json.xsl")
            sources = (data or {}).get('icestats', {}).get('source', [])
            # Icecast sends a single mount as an object, not a list
            if isinstance(sources, dict):
                sources = [sources]
            for source in sources:
                if source.get('title') and source.get('server_description'):
                    return {
                        'title': source.get('title', 'Unknown Track'),
                        'artist': '',
                        'album': '',
                        'station': f"{source.get('server_description')} ({source.get('bitrate')}kbps)",
                        'source': 'icecast'
                    }

        return None

    async def _update_metadata_loop(self):
        """Background task to periodically update metadata.

        Runs while a stream is set, also while the browser has it paused, so
        track info continues after a resume.
        """
        while self.current_audio_stream:
            try:
                stream_url = self.current_audio_stream
                stream_info = self._detect_stream_type(stream_url)
                metadata = None
                if stream_info:
                    metadata = await self._fetch_metadata(stream_info)
                # No station-specific API (or it gave us nothing): fall back
                # to the stream's own ICY metadata, which most Icecast and
                # Shoutcast stations broadcast.
                if not metadata:
                    metadata = await self._fetch_icy_metadata(self.current_resolved_url or stream_url)

                if metadata and self.current_audio_stream == stream_url:
                    metadata['last_updated'] = datetime.now().isoformat()
                    self.current_metadata = metadata
                    logging.debug(f"Updated metadata: {metadata['title']} by {metadata['artist']}")

                    # Drive the canvas now-playing card, but only when the
                    # track actually changed (avoid restarting the marquee
                    # / re-rendering every 15s poll).
                    key = (metadata.get('title'), metadata.get('artist'))
                    if metadata.get('title') and key != self._last_published_key:
                        self._last_published_key = key
                        await self._publish_card()

                await asyncio.sleep(METADATA_UPDATE_INTERVAL)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logging.warning(f"Metadata update failed: {e}")
                await asyncio.sleep(30)

    def now_playing_payload(self) -> Optional[Dict[str, Any]]:
        """Now-playing card data for the current audio stream, or None.

        Live track metadata when a metadata-bearing stream provides it,
        otherwise just the friendly station name (the React view shows it over
        a generic radio backdrop). Returns None for local sound-effect clips
        and when nothing is playing. Used both to drive the card and to replay
        state to a freshly-connected client so it's never blank.
        """
        if not self.current_audio_stream:
            return None
        host = (urlparse(self.current_audio_stream).hostname or "").lower()
        if not host or self._is_local_host(host):
            return None
        md = self.current_metadata
        if md.get("title"):
            name, artists, album = md["title"], md.get("artist", ""), md.get("station", "")
        else:
            name, artists, album = self._get_friendly_stream_name(self.current_audio_stream), "", ""
        return {
            "name": name,
            "artists": artists,
            "album": album,
            "album_art_url": self._current_art_url,
            "duration_ms": 0,
            "spotify_url": None,
        }

    async def _publish_card(self):
        """Show the current stream on the canvas now-playing card.

        Reuses the same `track_changed` event + `radio` display type that the
        NowPlaying React view already renders for Spotify/Sendspin/Bluetooth.
        The station logo doubles as the album art (blurred backdrop + cover);
        radio has no track duration, so the progress bar/QR stay hidden.
        Does nothing for local sound-effect clips.
        """
        payload = self.now_playing_payload()
        if not payload:
            return
        if self.now_playing_ws:
            await self.now_playing_ws.broadcast("track_changed", payload)
        # First card for this stream: swap the static logo overlay for the card.
        if self.display_stack and not self._radio_card_active:
            await self.display_stack.push("radio", {}, item_id="radio")
            await self.display_stack.remove("audio-art")
            self._radio_card_active = True
            logging.info(f"Audio now-playing card shown: {payload['name']}")

    def start_metadata_updates(self):
        """Start the metadata update background task"""
        if self.metadata_task:
            self.metadata_task.cancel()
        self.metadata_task = asyncio.create_task(self._update_metadata_loop())

    def stop_metadata_updates(self):
        """Stop the metadata update background task"""
        if self.metadata_task:
            self.metadata_task.cancel()
            self.metadata_task = None
        self.current_metadata = {}
