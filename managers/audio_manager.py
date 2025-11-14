"""
Audio Manager

Handles audio streaming via MPV pool with metadata extraction and volume control.
"""
import asyncio
import logging
import aiohttp
from datetime import datetime
from typing import Optional, Dict, Any
from urllib.parse import urlparse

from managers.mpv_pools import AudioMPVPool
from managers.mpv_controller import MPVController
from config import AUDIO_DEVICE


class AudioManager:
    """Manages audio streaming using the audio MPV pool"""

    def __init__(self, audio_pool: AudioMPVPool, background_manager=None):
        """
        Initialize Audio Manager

        Args:
            audio_pool: AudioMPVPool instance for audio playback
            background_manager: Optional BackgroundManager for updating display
        """
        self.audio_pool = audio_pool
        self.background_manager = background_manager

        # Current audio state
        self.audio_controller: Optional[MPVController] = None
        self.current_audio_stream: Optional[str] = None
        self.audio_volume: int = 80

        # Metadata
        self.current_metadata: Dict[str, Any] = {}
        self.metadata_task: Optional[asyncio.Task] = None

    async def _resolve_audio_url(self, stream_url: str) -> str:
        """Resolve PLS/M3U playlist URLs to direct stream URLs"""
        try:
            if stream_url.endswith('.pls'):
                # Parse PLS playlist format
                async with aiohttp.ClientSession() as session:
                    async with session.get(stream_url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                        if response.status == 200:
                            content = await response.text()
                            for line in content.split('\n'):
                                if line.startswith('File1='):
                                    direct_url = line.split('=', 1)[1].strip()
                                    logging.info(f"Resolved PLS URL {stream_url} to {direct_url}")
                                    return direct_url
            elif stream_url.endswith('.m3u') or stream_url.endswith('.m3u8'):
                # Parse M3U playlist format
                async with aiohttp.ClientSession() as session:
                    async with session.get(stream_url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                        if response.status == 200:
                            content = await response.text()
                            for line in content.split('\n'):
                                line = line.strip()
                                if line and not line.startswith('#'):
                                    logging.info(f"Resolved M3U URL {stream_url} to {line}")
                                    return line

            # Return original URL if not a playlist or parsing failed
            return stream_url

        except Exception as e:
            logging.warning(f"Failed to resolve playlist URL {stream_url}: {e}")
            return stream_url

    async def start_audio_stream(self, stream_url: str, volume: Optional[int] = None) -> bool:
        """Start audio streaming using IPC-controlled mpv process"""
        try:
            # Stop any existing audio stream
            if self.audio_controller:
                await self.stop_audio_stream()

            # Use provided volume or current setting
            if volume is not None:
                self.audio_volume = max(0, min(100, volume))

            # Resolve playlist URLs to direct stream URLs
            resolved_url = await self._resolve_audio_url(stream_url)

            # Get an available mpv controller from the pool
            controller = await self.audio_pool.get_available_controller()
            if not controller:
                logging.error(f"No available mpv processes in pool for audio stream: {stream_url}")
                logging.error(f"Pool status: {len(self.audio_pool.processes)} total processes, "
                            f"{len([p for p in self.audio_pool.controllers.values() if p.in_use])} in use")
                return False

            logging.info(f"Starting audio stream: {resolved_url} (original: {stream_url}) at volume {self.audio_volume}")

            # Configure for audio-only playback
            await controller.send_command(["set", "video", "no"])
            await controller.send_command(["set", "audio-device", AUDIO_DEVICE])

            # Load the audio stream
            result = await controller.send_command(["loadfile", resolved_url])
            if result.get("error") and result.get("error") != "success":
                error_msg = result.get("error", "Unknown loadfile error")
                logging.error(f"Failed to load audio stream {resolved_url}: {error_msg}")
                await self.audio_pool.release_controller(controller)
                return False

            # Give it a moment to load
            await asyncio.sleep(0.5)

            # Set volume before starting playback
            await controller.send_command(["set", "volume", str(self.audio_volume)])

            # CRITICAL: Explicitly unpause to start playback in idle mode
            # MPV in idle mode doesn't auto-play after loadfile - we must explicitly unpause
            await controller.send_command(["set_property", "pause", False])

            # Verify playback started
            pause_response = await controller.get_property("pause")
            is_paused = pause_response.get("data", True) if pause_response else True

            if pause_response and pause_response.get("error") and pause_response.get("error") != "success":
                error_msg = pause_response.get("error", "Unknown pause property error")
                logging.error(f"Failed to check playback status for {stream_url}: {error_msg}")

            if not is_paused:
                self.current_audio_stream = stream_url
                self.audio_controller = controller

                logging.info(f"Audio stream started successfully: {stream_url}")
                logging.info(f"Using mpv process ID: {controller.process_id}, volume: {self.audio_volume}")

                # Start metadata updates
                self.start_metadata_updates()

                # Update background to show audio icon
                if self.background_manager:
                    await self.background_manager.start_static_mode_with_audio_status(show_audio_icon=True)

                return True
            else:
                logging.error(f"Audio stream failed to start playing: {stream_url} (is_paused: {is_paused})")
                if pause_response:
                    logging.error(f"Pause response details: {pause_response}")
                await self.audio_pool.release_controller(controller)
                return False

        except Exception as e:
            logging.error(f"Failed to start audio stream {stream_url}: {type(e).__name__}: {e}")
            logging.error(f"Audio stream error details - resolved_url: {resolved_url if 'resolved_url' in locals() else 'N/A'}, volume: {self.audio_volume}")
            if 'controller' in locals():
                try:
                    await self.audio_pool.release_controller(controller)
                    logging.info(f"Released mpv controller {controller.process_id} after error")
                except Exception as release_error:
                    logging.error(f"Failed to release mpv controller after audio stream error: {release_error}")
            return False

    async def stop_audio_stream(self) -> bool:
        """Stop the current audio stream using IPC"""
        try:
            if self.audio_controller:
                logging.info("Stopping audio stream")

                # Stop playback via IPC
                await self.audio_controller.send_command(["stop"])

                # Release the controller back to the pool
                await self.audio_pool.release_controller(self.audio_controller)

                # Clean up references
                self.audio_controller = None
                self.current_audio_stream = None

                logging.info("Audio stream stopped")

                # Stop metadata updates
                self.stop_metadata_updates()

                # Update background to remove audio icon
                if self.background_manager:
                    await self.background_manager.start_static_mode_with_audio_status(show_audio_icon=False)

                return True
            else:
                logging.info("No audio stream to stop")
                return True

        except Exception as e:
            logging.error(f"Failed to stop audio stream: {type(e).__name__}: {e}")
            logging.error(f"Current stream: {self.current_audio_stream}")
            if self.audio_controller:
                try:
                    await self.audio_pool.release_controller(self.audio_controller)
                    logging.info(f"Released mpv controller {self.audio_controller.process_id} after stop error")
                except Exception as release_error:
                    logging.error(f"Failed to release mpv process after stop error: {release_error}")
            self.audio_controller = None
            self.current_audio_stream = None
            return False

    async def set_volume(self, volume: int) -> bool:
        """Set audio volume (0-100)"""
        try:
            self.audio_volume = max(0, min(100, volume))

            if self.audio_controller:
                await self.audio_controller.send_command(["set", "volume", str(self.audio_volume)])
                logging.info(f"Set audio volume to {self.audio_volume}")

            return True
        except Exception as e:
            logging.error(f"Failed to set volume: {e}")
            return False

    def get_audio_status(self) -> Dict[str, Any]:
        """Get current audio streaming status"""
        is_playing = self.audio_controller is not None

        # Get a user-friendly stream name
        stream_name = None
        if is_playing and self.current_audio_stream:
            stream_name = self._get_friendly_stream_name(self.current_audio_stream)

        status = {
            "is_playing": is_playing,
            "current_stream": self.current_audio_stream if is_playing else None,
            "stream_name": stream_name,
            "volume": self.audio_volume,
            "process_id": self.audio_controller.process_id if is_playing else None
        }

        # Add metadata if available
        if is_playing and self.current_metadata:
            status["metadata"] = self.current_metadata

        return status

    def _get_friendly_stream_name(self, stream_url: str) -> str:
        """Convert stream URL to a user-friendly name"""
        if not stream_url:
            return "Unknown Stream"

        # Handle common streaming services
        if "soma.fm" in stream_url.lower() or "somafm" in stream_url.lower():
            # Extract station name from soma.fm URLs
            parts = stream_url.split('/')
            for part in parts:
                if part and not part.startswith('http') and '.' not in part:
                    return f"SomaFM - {part.title()}"
            return "SomaFM"
        elif "radio" in stream_url.lower():
            return "Radio Stream"
        elif stream_url.startswith("http"):
            # Try to extract hostname
            try:
                parsed = urlparse(stream_url)
                hostname = parsed.hostname or "Unknown"
                return f"Stream from {hostname}"
            except:
                return "Audio Stream"
        else:
            return "Audio Stream"

    def _detect_stream_type(self, stream_url: str) -> Optional[Dict[str, Any]]:
        """Detect the type of audio stream for metadata fetching"""
        if not stream_url:
            return None

        # SomaFM detection
        if "soma.fm" in stream_url.lower() or "somafm" in stream_url.lower():
            # Extract station name
            parts = stream_url.split('/')
            for part in parts:
                if part and not part.startswith('http') and '.' not in part and part not in ['pls', 'm3u', 'mp3']:
                    return {"type": "somafm", "station": part.lower()}
            return {"type": "somafm", "station": "groovesalad"}  # default

        # Radio Paradise detection
        if "radioparadise.com" in stream_url.lower():
            # Detect channel from URL
            if "mellow" in stream_url.lower():
                channel = 1
            elif "rock" in stream_url.lower():
                channel = 2
            elif "global" in stream_url.lower():
                channel = 3
            else:
                channel = 0  # main mix
            return {"type": "radioparadise", "channel": channel}

        # Icecast detection
        if "icecast" in stream_url.lower() or ":8000" in stream_url:
            # Extract server URL
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
                            # Find active stream with title info
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
        while self.audio_controller:
            try:
                if self.current_audio_stream:
                    stream_info = self._detect_stream_type(self.current_audio_stream)
                    if stream_info:
                        metadata = await self._fetch_metadata(stream_info)
                        if metadata:
                            metadata['last_updated'] = datetime.now().isoformat()
                            self.current_metadata = metadata
                            logging.debug(f"Updated metadata: {metadata['title']} by {metadata['artist']}")

                # Wait 15 seconds before next update
                await asyncio.sleep(15)

            except Exception as e:
                logging.warning(f"Metadata update failed: {e}")
                await asyncio.sleep(30)  # Wait longer on error

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
