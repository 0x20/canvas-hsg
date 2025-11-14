"""
Chromecast Manager

Manages casting media to Chromecast devices on the network.
Integrates with audio and playback managers to stop local playback when casting starts.
"""
import asyncio
import logging
import time
import re
from typing import Optional, Dict, Any, List
from urllib.parse import urlparse, parse_qs

import pychromecast
from pychromecast.controllers.media import MediaController
from pychromecast.quick_play import quick_play


class ChromecastManager:
    """Manages Chromecast device discovery and media casting"""

    def __init__(self, audio_manager=None, playback_manager=None):
        """
        Initialize Chromecast Manager

        Args:
            audio_manager: Optional AudioManager to stop audio when casting starts
            playback_manager: Optional PlaybackManager to stop video when casting starts
        """
        self.audio_manager = audio_manager
        self.playback_manager = playback_manager

        # Chromecast state
        self.chromecasts: List[pychromecast.Chromecast] = []
        self.current_cast: Optional[pychromecast.Chromecast] = None
        self.media_controller: Optional[MediaController] = None
        self.discovery_running = False
        self.last_discovery_time = 0
        self.discovery_cache_duration = 60  # Cache discovery results for 60 seconds
        self.browser = None  # Keep browser alive for Chromecast connections

        # Current cast state
        self.current_media_url: Optional[str] = None
        self.current_media_type: Optional[str] = None  # 'audio' or 'video'
        self.is_casting = False

    async def discover_devices(self, timeout: int = 5) -> List[Dict[str, Any]]:
        """
        Discover Chromecast devices on the network

        Args:
            timeout: Discovery timeout in seconds

        Returns:
            List of discovered Chromecast devices with their info
        """
        try:
            # Check cache to avoid too frequent discoveries
            current_time = time.time()
            if self.chromecasts and (current_time - self.last_discovery_time) < self.discovery_cache_duration:
                logging.info(f"Using cached Chromecast discovery results ({len(self.chromecasts)} devices)")
                return self._format_device_list(self.chromecasts)

            logging.info(f"Discovering Chromecast devices (timeout={timeout}s)...")
            self.discovery_running = True

            # Stop old browser if exists
            if self.browser:
                try:
                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(None, self.browser.stop_discovery)
                except Exception as e:
                    logging.debug(f"Error stopping old browser: {e}")

            # Run discovery in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            chromecasts, browser = await loop.run_in_executor(
                None,
                lambda: pychromecast.get_chromecasts(timeout=timeout)
            )

            # Keep the browser alive for Chromecast connections
            self.browser = browser

            self.chromecasts = list(chromecasts)
            self.last_discovery_time = current_time
            self.discovery_running = False

            logging.info(f"Discovered {len(self.chromecasts)} Chromecast device(s)")
            return self._format_device_list(self.chromecasts)

        except Exception as e:
            logging.error(f"Failed to discover Chromecast devices: {e}")
            self.discovery_running = False
            return []

    def _format_device_list(self, chromecasts: List[pychromecast.Chromecast]) -> List[Dict[str, Any]]:
        """Format Chromecast device list for API response"""
        devices = []
        for cast in chromecasts:
            try:
                # Get host and port from cast_info
                host = cast.cast_info.host if hasattr(cast, 'cast_info') else cast.uri.split(':')[0]
                port = cast.cast_info.port if hasattr(cast, 'cast_info') else 8009

                devices.append({
                    "name": cast.name,
                    "model": cast.model_name,
                    "uuid": str(cast.uuid),
                    "host": host,
                    "port": port,
                    "status": cast.status.status_text if cast.status else "unknown"
                })
            except Exception as e:
                logging.warning(f"Error formatting device {cast.name}: {e}")
                # Add minimal info
                devices.append({
                    "name": cast.name,
                    "model": getattr(cast, 'model_name', 'unknown'),
                    "uuid": str(getattr(cast, 'uuid', 'unknown')),
                    "host": "unknown",
                    "port": 8009,
                    "status": "unknown"
                })
        return devices

    def _detect_media_type(self, media_url: str) -> str:
        """
        Detect if media URL is audio or video based on file extension and URL patterns

        Args:
            media_url: Media URL to analyze

        Returns:
            'audio' or 'video'
        """
        # Parse URL
        parsed = urlparse(media_url.lower())
        path = parsed.path

        # Common audio file extensions
        audio_extensions = ['.mp3', '.m4a', '.aac', '.ogg', '.opus', '.flac', '.wav', '.wma']
        # Common video file extensions
        video_extensions = ['.mp4', '.mkv', '.webm', '.avi', '.mov', '.m4v', '.flv', '.wmv']

        # Check file extension
        for ext in audio_extensions:
            if path.endswith(ext):
                return 'audio'

        for ext in video_extensions:
            if path.endswith(ext):
                return 'video'

        # Check for streaming patterns
        if any(pattern in media_url.lower() for pattern in ['.pls', '.m3u', 'radio', 'somafm', 'audio']):
            return 'audio'

        if any(pattern in media_url.lower() for pattern in ['youtube', 'youtu.be', 'vimeo', 'video']):
            return 'video'

        # Default to video for unknown types
        return 'video'

    def _extract_youtube_id(self, youtube_url: str) -> Optional[str]:
        """
        Extract YouTube video ID from various YouTube URL formats

        Args:
            youtube_url: YouTube video URL

        Returns:
            YouTube video ID or None if extraction fails
        """
        # Handle youtu.be/VIDEO_ID format
        if 'youtu.be/' in youtube_url:
            match = re.search(r'youtu\.be/([a-zA-Z0-9_-]+)', youtube_url)
            if match:
                return match.group(1)

        # Handle youtube.com/watch?v=VIDEO_ID format
        if 'youtube.com/watch' in youtube_url:
            parsed = urlparse(youtube_url)
            params = parse_qs(parsed.query)
            if 'v' in params:
                return params['v'][0]

        return None

    async def start_cast(self, media_url: str, device_name: Optional[str] = None,
                         content_type: Optional[str] = None, title: Optional[str] = None) -> bool:
        """
        Start casting media to a Chromecast device

        Args:
            media_url: URL of the media to cast (YouTube URLs supported natively)
            device_name: Name of the Chromecast device (uses first found if None)
            content_type: MIME type of content (auto-detected if None)
            title: Display title for the media

        Returns:
            True if casting started successfully
        """
        try:
            # Check if this is a YouTube URL
            is_youtube = 'youtube.com/watch' in media_url or 'youtu.be/' in media_url

            # Ensure we have discovered devices
            if not self.chromecasts:
                await self.discover_devices()

            if not self.chromecasts:
                logging.error("No Chromecast devices found on the network")
                return False

            # Select device
            if device_name:
                cast = next((c for c in self.chromecasts if c.name == device_name), None)
                if not cast:
                    logging.error(f"Chromecast device '{device_name}' not found")
                    return False
            else:
                cast = self.chromecasts[0]
                logging.info(f"Using first available Chromecast: {cast.name}")

            # Detect media type (audio vs video)
            media_type = self._detect_media_type(media_url)
            logging.info(f"Detected media type: {media_type} for URL: {media_url}")

            # Stop local playback based on media type
            if media_type == 'video':
                # Video casting - stop both audio and video playback
                logging.info("Stopping local audio and video playback for video cast")
                if self.audio_manager:
                    await self.audio_manager.stop_audio_stream()
                if self.playback_manager:
                    await self.playback_manager.stop_playback()
            else:
                # Audio casting - only stop video playback
                logging.info("Stopping local video playback for audio cast")
                if self.playback_manager:
                    await self.playback_manager.stop_playback()

            # Ensure device is connected and ready
            logging.info(f"Connecting to Chromecast: {cast.name}")
            loop = asyncio.get_event_loop()

            # Check if we need to call wait() or if it's already been called
            try:
                await loop.run_in_executor(None, lambda: cast.wait(timeout=10))
            except RuntimeError as e:
                if "threads can only be started once" in str(e):
                    # Threads already started from discovery, wait for connection status instead
                    logging.info(f"Chromecast {cast.name} threads already started, waiting for connection...")
                    # Give it time to connect
                    for i in range(20):  # Wait up to 10 seconds
                        await asyncio.sleep(0.5)
                        if cast.socket_client and cast.socket_client.is_connected:
                            logging.info(f"Chromecast {cast.name} connected")
                            break
                    else:
                        logging.error(f"Chromecast {cast.name} failed to connect after 10s")
                        return False
                else:
                    raise

            # Get media controller
            mc = cast.media_controller

            # Auto-detect content type if not provided
            if not content_type:
                if media_type == 'audio':
                    # Try common audio formats
                    if media_url.endswith('.mp3'):
                        content_type = 'audio/mp3'
                    elif media_url.endswith('.m4a'):
                        content_type = 'audio/mp4'
                    else:
                        content_type = 'audio/mp3'  # Default
                else:
                    # Try common video formats
                    if media_url.endswith('.mp4') or media_url.endswith('.m4v'):
                        content_type = 'video/mp4'
                    elif media_url.endswith('.webm'):
                        content_type = 'video/webm'
                    else:
                        content_type = 'video/mp4'  # Default

            # Set title
            if not title:
                title = f"HSG Canvas - {media_type.title()} Stream"

            # Start casting - use YouTube app for YouTube URLs, media controller for others
            if is_youtube:
                # Extract YouTube video ID
                video_id = self._extract_youtube_id(media_url)
                if not video_id:
                    logging.error(f"Failed to extract YouTube video ID from: {media_url}")
                    return False

                logging.info(f"Starting YouTube cast: video_id={video_id} on {cast.name}")

                # Use quick_play for native YouTube support
                await loop.run_in_executor(
                    None,
                    lambda: quick_play(cast, "youtube", {"media_id": video_id})
                )

                # Wait a moment for YouTube app to load
                await asyncio.sleep(3)
            else:
                # Regular media - use media controller
                logging.info(f"Starting media cast: {media_url} ({content_type}) on {cast.name}")
                await loop.run_in_executor(
                    None,
                    lambda: mc.play_media(media_url, content_type, title=title)
                )

                # Wait a moment for cast to start
                await asyncio.sleep(2)

                # Block until media is loaded
                await loop.run_in_executor(None, mc.block_until_active)

            # Store current state
            self.current_cast = cast
            self.media_controller = mc
            self.current_media_url = media_url
            self.current_media_type = media_type
            self.is_casting = True

            logging.info(f"Successfully started casting to {cast.name}")
            return True

        except Exception as e:
            logging.error(f"Failed to start casting: {type(e).__name__}: {e}")
            import traceback
            logging.error(f"Traceback: {traceback.format_exc()}")
            return False

    async def stop_cast(self) -> bool:
        """Stop the current cast"""
        try:
            if not self.current_cast or not self.media_controller:
                logging.info("No active cast to stop")
                return True

            logging.info(f"Stopping cast on {self.current_cast.name}")

            # Stop media playback
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self.media_controller.stop)

            # Clear state
            self.current_cast = None
            self.media_controller = None
            self.current_media_url = None
            self.current_media_type = None
            self.is_casting = False

            logging.info("Cast stopped successfully")
            return True

        except Exception as e:
            logging.error(f"Failed to stop cast: {e}")
            # Clear state anyway
            self.current_cast = None
            self.media_controller = None
            self.current_media_url = None
            self.current_media_type = None
            self.is_casting = False
            return False

    async def pause_cast(self) -> bool:
        """Pause the current cast"""
        try:
            if not self.media_controller:
                logging.error("No active cast to pause")
                return False

            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self.media_controller.pause)

            logging.info("Cast paused")
            return True

        except Exception as e:
            logging.error(f"Failed to pause cast: {e}")
            return False

    async def play_cast(self) -> bool:
        """Resume/play the current cast"""
        try:
            if not self.media_controller:
                logging.error("No active cast to play")
                return False

            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self.media_controller.play)

            logging.info("Cast resumed")
            return True

        except Exception as e:
            logging.error(f"Failed to play cast: {e}")
            return False

    async def set_volume(self, volume: float) -> bool:
        """
        Set Chromecast volume

        Args:
            volume: Volume level (0.0 to 1.0)

        Returns:
            True if successful
        """
        try:
            if not self.current_cast:
                logging.error("No active Chromecast to set volume")
                return False

            volume = max(0.0, min(1.0, volume))
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, lambda: self.current_cast.set_volume(volume))

            logging.info(f"Set Chromecast volume to {volume}")
            return True

        except Exception as e:
            logging.error(f"Failed to set Chromecast volume: {e}")
            return False

    def get_cast_status(self) -> Dict[str, Any]:
        """Get current casting status"""
        status = {
            "is_casting": self.is_casting,
            "device_name": self.current_cast.name if self.current_cast else None,
            "media_url": self.current_media_url,
            "media_type": self.current_media_type,
            "available_devices": len(self.chromecasts)
        }

        # Add media controller status if available
        if self.media_controller and self.current_cast:
            try:
                mc_status = self.media_controller.status
                status["player_state"] = mc_status.player_state if mc_status else "UNKNOWN"
                status["volume"] = self.current_cast.status.volume_level if self.current_cast.status else None
                status["duration"] = mc_status.duration if mc_status else None
                status["current_time"] = mc_status.current_time if mc_status else None
            except Exception as e:
                logging.debug(f"Could not get detailed cast status: {e}")

        return status

    async def cleanup(self):
        """Cleanup Chromecast connections"""
        try:
            if self.current_cast:
                await self.stop_cast()

            # Stop discovery browser
            if self.browser:
                try:
                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(None, self.browser.stop_discovery)
                except Exception as e:
                    logging.debug(f"Error stopping browser: {e}")

            # Disconnect all chromecasts
            for cast in self.chromecasts:
                try:
                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(None, cast.disconnect)
                except Exception as e:
                    logging.debug(f"Error disconnecting Chromecast {cast.name}: {e}")

            self.chromecasts = []
            self.browser = None
            logging.info("Chromecast manager cleaned up")

        except Exception as e:
            logging.error(f"Error during Chromecast cleanup: {e}")
