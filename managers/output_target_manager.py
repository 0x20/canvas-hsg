"""
Output Target Manager

Manages all output targets for audio and video playback.
Provides unified interface for local (HDMI/Audio Hat) and remote (Chromecast) outputs.
"""
import asyncio
import logging
from typing import Dict, List, Optional, Any
from enum import Enum


class TargetType(str, Enum):
    """Types of output targets"""
    LOCAL_VIDEO = "local-video"
    LOCAL_AUDIO = "local-audio"
    CHROMECAST = "chromecast"


class OutputTarget:
    """Represents a single output target"""

    def __init__(self, target_id: str, target_type: TargetType, name: str,
                 capabilities: List[str], metadata: Optional[Dict[str, Any]] = None):
        """
        Initialize output target

        Args:
            target_id: Unique identifier for this target
            target_type: Type of target (local or chromecast)
            name: Human-readable name
            capabilities: List of capabilities ['audio', 'video']
            metadata: Additional target information
        """
        self.target_id = target_id
        self.target_type = target_type
        self.name = name
        self.capabilities = capabilities
        self.metadata = metadata or {}
        self.is_available = True

    def to_dict(self) -> Dict[str, Any]:
        """Convert target to dictionary for API responses"""
        return {
            "id": self.target_id,
            "type": self.target_type,
            "name": self.name,
            "capabilities": self.capabilities,
            "is_available": self.is_available,
            "metadata": self.metadata
        }


class OutputTargetManager:
    """
    Manages all output targets and routes playback to appropriate destination

    Keeps Chromecast code isolated from core Canvas functionality
    """

    def __init__(self, audio_manager=None, playback_manager=None, chromecast_manager=None):
        """
        Initialize Output Target Manager

        Args:
            audio_manager: Local audio playback manager
            playback_manager: Local video playback manager
            chromecast_manager: Chromecast casting manager
        """
        self.audio_manager = audio_manager
        self.playback_manager = playback_manager
        self.chromecast_manager = chromecast_manager

        # Available targets
        self.targets: Dict[str, OutputTarget] = {}

        # Default targets
        self.default_video_target = "local-video"
        self.default_audio_target = "local-audio"

        # Current active targets
        self.active_video_target: Optional[str] = None
        self.active_audio_target: Optional[str] = None

        # Auto-discovery settings
        self.auto_discover_interval = 300  # 5 minutes
        self.discovery_task: Optional[asyncio.Task] = None

        # Initialize local targets
        self._initialize_local_targets()

    def _initialize_local_targets(self):
        """Initialize local output targets (HDMI, Audio Hat)"""
        # Local video output (HDMI via DRM/MPV)
        self.targets["local-video"] = OutputTarget(
            target_id="local-video",
            target_type=TargetType.LOCAL_VIDEO,
            name="HDMI Display (Local)",
            capabilities=["video", "audio"],
            metadata={
                "device": "/dev/dri/card1",
                "connector": "HDMI-A-1",
                "resolution": "1920x1200",
                "is_default": True
            }
        )

        # Local audio output (Audio Hat via PulseAudio)
        self.targets["local-audio"] = OutputTarget(
            target_id="local-audio",
            target_type=TargetType.LOCAL_AUDIO,
            name="Audio Hat (Local)",
            capabilities=["audio"],
            metadata={
                "device": "pulse",
                "is_default": True
            }
        )

        logging.info("Initialized local output targets: HDMI Display, Audio Hat")

    async def discover_chromecast_targets(self) -> int:
        """
        Discover Chromecast devices and add them as targets

        Returns:
            Number of Chromecasts discovered
        """
        if not self.chromecast_manager:
            logging.warning("ChromecastManager not available, skipping discovery")
            return 0

        try:
            logging.info("Discovering Chromecast targets...")
            devices = await self.chromecast_manager.discover_devices()

            # Remove old chromecast targets
            old_targets = [tid for tid, target in self.targets.items()
                          if target.target_type == TargetType.CHROMECAST]
            for tid in old_targets:
                del self.targets[tid]

            # Add discovered chromecasts as targets
            for device in devices:
                target_id = f"chromecast-{device['uuid']}"
                self.targets[target_id] = OutputTarget(
                    target_id=target_id,
                    target_type=TargetType.CHROMECAST,
                    name=f"{device['name']} (Chromecast)",
                    capabilities=["video", "audio"],  # Chromecasts support both
                    metadata={
                        "uuid": device['uuid'],
                        "model": device['model'],
                        "host": device['host'],
                        "port": device['port'],
                        "device_name": device['name']
                    }
                )

            logging.info(f"Discovered {len(devices)} Chromecast target(s)")
            return len(devices)

        except Exception as e:
            logging.error(f"Failed to discover Chromecast targets: {e}")
            return 0

    async def start_auto_discovery(self):
        """Start periodic auto-discovery of Chromecasts"""
        if self.discovery_task:
            logging.warning("Auto-discovery already running")
            return

        async def discovery_loop():
            while True:
                try:
                    await asyncio.sleep(self.auto_discover_interval)
                    await self.discover_chromecast_targets()
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logging.error(f"Error in auto-discovery: {e}")

        self.discovery_task = asyncio.create_task(discovery_loop())
        logging.info(f"Started Chromecast auto-discovery (interval: {self.auto_discover_interval}s)")

    async def stop_auto_discovery(self):
        """Stop periodic auto-discovery"""
        if self.discovery_task:
            self.discovery_task.cancel()
            try:
                await self.discovery_task
            except asyncio.CancelledError:
                pass
            self.discovery_task = None
            logging.info("Stopped Chromecast auto-discovery")

    def get_all_targets(self) -> List[Dict[str, Any]]:
        """Get list of all available targets"""
        return [target.to_dict() for target in self.targets.values()]

    def get_target(self, target_id: str) -> Optional[OutputTarget]:
        """Get specific target by ID"""
        return self.targets.get(target_id)

    def get_targets_by_capability(self, capability: str) -> List[OutputTarget]:
        """Get all targets that support a specific capability"""
        return [target for target in self.targets.values()
                if capability in target.capabilities and target.is_available]

    async def play_video(self, video_url: str, target_id: Optional[str] = None,
                         duration: Optional[int] = None, **kwargs) -> bool:
        """
        Play video on specified target

        Args:
            video_url: URL of video to play
            target_id: Target ID (uses default if None)
            duration: Optional duration limit
            **kwargs: Additional parameters for playback

        Returns:
            True if playback started successfully
        """
        # Use default if no target specified
        if not target_id:
            target_id = self.default_video_target

        target = self.get_target(target_id)
        if not target:
            logging.error(f"Video target not found: {target_id}")
            return False

        if "video" not in target.capabilities:
            logging.error(f"Target {target_id} does not support video playback")
            return False

        # Route to appropriate manager
        if target.target_type == TargetType.LOCAL_VIDEO:
            # Local HDMI playback
            if not self.playback_manager:
                logging.error("PlaybackManager not available")
                return False

            logging.info(f"Playing video on local HDMI: {video_url}")
            success = await self.playback_manager.play_youtube(video_url, duration=duration, **kwargs)
            if success:
                self.active_video_target = target_id
            return success

        elif target.target_type == TargetType.CHROMECAST:
            # Chromecast playback
            if not self.chromecast_manager:
                logging.error("ChromecastManager not available")
                return False

            device_name = target.metadata.get("device_name")
            logging.info(f"Casting video to Chromecast: {device_name}")

            # Filter kwargs to only include Chromecast-supported parameters
            chromecast_kwargs = {}
            if "content_type" in kwargs:
                chromecast_kwargs["content_type"] = kwargs["content_type"]
            if "title" in kwargs:
                chromecast_kwargs["title"] = kwargs["title"]

            success = await self.chromecast_manager.start_cast(
                video_url,
                device_name=device_name,
                **chromecast_kwargs
            )
            if success:
                self.active_video_target = target_id
            return success

        return False

    async def play_audio(self, audio_url: str, target_id: Optional[str] = None,
                         volume: Optional[int] = None, **kwargs) -> bool:
        """
        Play audio on specified target

        Args:
            audio_url: URL of audio to play
            target_id: Target ID (uses default if None)
            volume: Optional volume level
            **kwargs: Additional parameters for playback

        Returns:
            True if playback started successfully
        """
        # Use default if no target specified
        if not target_id:
            target_id = self.default_audio_target

        target = self.get_target(target_id)
        if not target:
            logging.error(f"Audio target not found: {target_id}")
            return False

        if "audio" not in target.capabilities:
            logging.error(f"Target {target_id} does not support audio playback")
            return False

        # Route to appropriate manager
        if target.target_type == TargetType.LOCAL_AUDIO:
            # Local audio hat playback
            if not self.audio_manager:
                logging.error("AudioManager not available")
                return False

            logging.info(f"Playing audio on local audio hat: {audio_url}")
            success = await self.audio_manager.start_audio_stream(audio_url, volume=volume)
            if success:
                self.active_audio_target = target_id
            return success

        elif target.target_type == TargetType.CHROMECAST:
            # Chromecast playback
            if not self.chromecast_manager:
                logging.error("ChromecastManager not available")
                return False

            device_name = target.metadata.get("device_name")
            logging.info(f"Casting audio to Chromecast: {device_name}")

            # Filter kwargs to only include Chromecast-supported parameters
            chromecast_kwargs = {}
            if "content_type" in kwargs:
                chromecast_kwargs["content_type"] = kwargs["content_type"]
            if "title" in kwargs:
                chromecast_kwargs["title"] = kwargs["title"]

            success = await self.chromecast_manager.start_cast(
                audio_url,
                device_name=device_name,
                **chromecast_kwargs
            )
            if success:
                self.active_audio_target = target_id
            return success

        return False

    async def stop_playback(self, media_type: str = "all"):
        """
        Stop playback on active targets

        Args:
            media_type: 'video', 'audio', or 'all'
        """
        if media_type in ["video", "all"] and self.active_video_target:
            target = self.get_target(self.active_video_target)
            if target:
                if target.target_type == TargetType.LOCAL_VIDEO and self.playback_manager:
                    await self.playback_manager.stop_playback()
                elif target.target_type == TargetType.CHROMECAST and self.chromecast_manager:
                    await self.chromecast_manager.stop_cast()
            self.active_video_target = None

        if media_type in ["audio", "all"] and self.active_audio_target:
            target = self.get_target(self.active_audio_target)
            if target:
                if target.target_type == TargetType.LOCAL_AUDIO and self.audio_manager:
                    await self.audio_manager.stop_audio_stream()
                elif target.target_type == TargetType.CHROMECAST and self.chromecast_manager:
                    await self.chromecast_manager.stop_cast()
            self.active_audio_target = None

    def get_status(self) -> Dict[str, Any]:
        """Get current output target status"""
        return {
            "total_targets": len(self.targets),
            "available_targets": len([t for t in self.targets.values() if t.is_available]),
            "active_video_target": self.active_video_target,
            "active_audio_target": self.active_audio_target,
            "default_video_target": self.default_video_target,
            "default_audio_target": self.default_audio_target,
            "targets": self.get_all_targets()
        }

    async def cleanup(self):
        """Cleanup resources"""
        await self.stop_auto_discovery()
        await self.stop_playback("all")
        logging.info("OutputTargetManager cleaned up")
