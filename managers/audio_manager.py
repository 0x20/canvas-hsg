"""
Audio Manager

Handles audio streaming via browser <audio> element controlled by WebSocket.
Replaces MPV audio pool with WebSocket commands to the React AudioPlayer component.
"""
import asyncio
import logging
import os
import time
import aiohttp
import yaml
from datetime import datetime
from typing import Optional, Dict, Any
from urllib.parse import urlparse

from config import METADATA_UPDATE_INTERVAL


class AudioManager:
    """Manages audio streaming via browser WebSocket"""

    def __init__(self, audio_ws_manager):
        self.audio_ws_manager = audio_ws_manager
        self.playback_manager = None
        self.spotify_manager = None
        self.sendspin_manager = None
        self.bluetooth_manager = None
        # Display stack — used to show fullscreen station art for audio streams.
        self.display_stack = None
        # Cached SomaFM id→logo map (channels.json); extensions vary per station.
        self._somafm_logos: Dict[str, str] = {}
        self._somafm_logos_ts: float = 0.0
        # Cached url→image map from media_sources.yaml (built once; restart to
        # pick up edits, consistent with the rest of the config).
        self._stream_images: Optional[Dict[str, str]] = None

        # Current audio state
        self.current_audio_stream: Optional[str] = None
        self.audio_volume: int = 80
        self._is_playing: bool = False

        # Cached status from browser reports
        self._browser_status: Dict[str, Any] = {}

        # Metadata
        self.current_metadata: Dict[str, Any] = {}
        self.metadata_task: Optional[asyncio.Task] = None

    async def _resolve_audio_url(self, stream_url: str) -> str:
        """Resolve PLS/M3U playlist URLs to direct stream URLs"""
        try:
            if stream_url.endswith('.pls'):
                async with aiohttp.ClientSession() as session:
                    async with session.get(stream_url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                        if response.status == 200:
                            content = await response.text()
                            for line in content.split('\n'):
                                if line.startswith('File1='):
                                    direct_url = line.split('=', 1)[1].strip()
                                    logging.info(f"Resolved PLS URL {stream_url} to {direct_url}")
                                    return direct_url
            elif stream_url.endswith('.m3u') and not stream_url.endswith('.m3u8'):
                # M3U playlist (not HLS) - resolve to first stream URL
                async with aiohttp.ClientSession() as session:
                    async with session.get(stream_url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                        if response.status == 200:
                            content = await response.text()
                            for line in content.split('\n'):
                                line = line.strip()
                                if line and not line.startswith('#'):
                                    logging.info(f"Resolved M3U URL {stream_url} to {line}")
                                    return line

            # Return original URL for direct streams and .m3u8 (HLS handled by browser)
            return stream_url

        except Exception as e:
            logging.warning(f"Failed to resolve playlist URL {stream_url}: {e}")
            return stream_url

    async def start_audio_stream(self, stream_url: str, volume: Optional[int] = None) -> bool:
        """Start audio streaming via browser WebSocket"""
        try:
            # Stop video playback to enforce audio exclusivity
            if self.playback_manager and self.playback_manager.current_stream:
                logging.info("Stopping video playback before starting audio stream")
                await self.playback_manager.stop_playback()

            # Stop any existing audio stream
            if self.current_audio_stream:
                await self.stop_audio_stream()

            # Use provided volume or current setting
            if volume is not None:
                self.audio_volume = max(0, min(100, volume))

            # Resolve playlist URLs to direct stream URLs
            resolved_url = await self._resolve_audio_url(stream_url)

            logging.info(f"Starting audio stream via browser: {resolved_url} (original: {stream_url}) at volume {self.audio_volume}")

            # Send play command to browser via WebSocket
            await self.audio_ws_manager.broadcast_raw({
                "type": "audio_play",
                "url": resolved_url,
                "volume": self.audio_volume,
            })

            self.current_audio_stream = stream_url
            self._is_playing = True

            logging.info(f"Audio stream command sent: {stream_url}")

            # Start metadata updates
            self.start_metadata_updates()

            # Fullscreen station art (silent overlay — doesn't interrupt audio)
            if self.display_stack:
                art_url = await self._resolve_station_art(stream_url)
                if art_url:
                    await self.display_stack.push(
                        "image", {"image_url": art_url}, item_id="audio-art"
                    )
                    logging.info(f"Audio station art shown: {art_url}")

            return True

        except Exception as e:
            logging.error(f"Failed to start audio stream {stream_url}: {e}")
            return False

    async def stop_audio_stream(self) -> bool:
        """Stop the current audio stream via WebSocket"""
        try:
            if self.current_audio_stream or self._is_playing:
                logging.info("Stopping audio stream")

                await self.audio_ws_manager.broadcast_raw({
                    "type": "audio_stop",
                })

                self.current_audio_stream = None
                self._is_playing = False

                self.stop_metadata_updates()
                # Remove the fullscreen station art overlay
                if self.display_stack:
                    await self.display_stack.remove("audio-art")
                logging.info("Audio stream stopped")

            return True

        except Exception as e:
            logging.error(f"Failed to stop audio stream: {e}")
            self.current_audio_stream = None
            self._is_playing = False
            return False

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

    def get_audio_status(self) -> Dict[str, Any]:
        """Get current audio streaming status across all sources"""
        # Collect all active sources
        sources = [
            ("audio_stream", lambda: self._is_playing and self.current_audio_stream),
            ("spotify", lambda: self.spotify_manager and self.spotify_manager.is_playing),
            ("sendspin", lambda: self.sendspin_manager and self.sendspin_manager.is_playing),
            ("bluetooth", lambda: self.bluetooth_manager and self.bluetooth_manager.is_playing),
            ("youtube", lambda: self.playback_manager and self.playback_manager.current_stream),
        ]
        active_sources = [name for name, check in sources if check()]
        source_playing = len(active_sources) > 0

        status = {
            "is_playing": source_playing,
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

    def _load_stream_images(self) -> Dict[str, str]:
        """url→image map from media_sources.yaml, parsed once and cached."""
        if self._stream_images is None:
            images: Dict[str, str] = {}
            try:
                cfg = os.path.join(
                    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "media_sources.yaml",
                )
                with open(cfg) as f:
                    sources = yaml.safe_load(f) or {}
                for group in (sources.get("music_streams") or {}).values():
                    for entry in group or []:
                        if entry.get("url") and entry.get("image"):
                            images[entry["url"]] = entry["image"]
            except Exception as e:
                logging.debug(f"media_sources image load failed: {e}")
            self._stream_images = images
        return self._stream_images

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
                async with aiohttp.ClientSession() as session:
                    async with session.get(
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

        Order: explicit `image` in media_sources.yaml → SomaFM cover (from the
        API, keyed by station id) → site favicon. Streaming needs internet
        anyway, so remote art URLs are fine.
        """
        if not stream_url:
            return None

        # 1. Curated per-preset image from media_sources.yaml (cached)
        curated = self._load_stream_images().get(stream_url)
        if curated:
            return curated

        host = (urlparse(stream_url).hostname or "").lower()

        # 2. SomaFM: exact cover from the API, keyed by station id (the stream
        #    basename; bitrate suffixes are handled inside _somafm_logo).
        if "somafm" in host or "soma.fm" in host:
            seg = os.path.splitext(os.path.basename(urlparse(stream_url).path))[0]
            if seg:
                return await self._somafm_logo(seg)

        # 3. Favicon fallback (low-res, but better than a blank background)
        if host:
            return f"https://www.google.com/s2/favicons?domain={host}&sz=128"
        return None

    def _detect_stream_type(self, stream_url: str) -> Optional[Dict[str, Any]]:
        """Detect the type of audio stream for metadata fetching"""
        if not stream_url:
            return None

        if "soma.fm" in stream_url.lower() or "somafm" in stream_url.lower():
            parts = stream_url.split('/')
            for part in parts:
                if part and not part.startswith('http') and '.' not in part and part not in ['pls', 'm3u', 'mp3']:
                    return {"type": "somafm", "station": part.lower()}
            return {"type": "somafm", "station": "groovesalad"}

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

    async def _fetch_metadata(self, stream_info: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Fetch metadata from appropriate API"""
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                if stream_info['type'] == 'somafm':
                    url = f"https://somafm.com/songs/{stream_info['station']}.json"
                    async with session.get(url) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            if data.get('songs') and len(data['songs']) > 0:
                                current = data['songs'][0]
                                return {
                                    'title': current.get('title', 'Unknown Track'),
                                    'artist': current.get('artist', ''),
                                    'album': current.get('album', ''),
                                    'station': f"SomaFM {stream_info['station'].title()}",
                                    'source': 'somafm'
                                }

                elif stream_info['type'] == 'radioparadise':
                    url = f"https://api.radioparadise.com/api/now_playing?chan={stream_info['channel']}"
                    async with session.get(url) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            channel_names = ['Main Mix', 'Mellow Mix', 'Rock Mix', 'Global Mix']
                            return {
                                'title': data.get('title', 'Unknown Track'),
                                'artist': data.get('artist', ''),
                                'album': data.get('album', '') + (f" ({data.get('year')})" if data.get('year') else ''),
                                'station': f"Radio Paradise {channel_names[stream_info['channel']]}",
                                'source': 'radioparadise'
                            }

                elif stream_info['type'] == 'icecast':
                    url = f"{stream_info['server']}/status-json.xsl"
                    async with session.get(url) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            for source in data.get('icestats', {}).get('source', []):
                                if source.get('title') and source.get('server_description'):
                                    return {
                                        'title': source.get('title', 'Unknown Track'),
                                        'artist': '',
                                        'album': '',
                                        'station': f"{source.get('server_description')} ({source.get('bitrate')}kbps)",
                                        'source': 'icecast'
                                    }

        except Exception as e:
            logging.warning(f"Failed to fetch metadata: {e}")

        return None

    async def _update_metadata_loop(self):
        """Background task to periodically update metadata"""
        while self._is_playing:
            try:
                if self.current_audio_stream:
                    stream_info = self._detect_stream_type(self.current_audio_stream)
                    if stream_info:
                        metadata = await self._fetch_metadata(stream_info)
                        if metadata:
                            metadata['last_updated'] = datetime.now().isoformat()
                            self.current_metadata = metadata
                            logging.debug(f"Updated metadata: {metadata['title']} by {metadata['artist']}")

                await asyncio.sleep(METADATA_UPDATE_INTERVAL)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logging.warning(f"Metadata update failed: {e}")
                await asyncio.sleep(30)

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
