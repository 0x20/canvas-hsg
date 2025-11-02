"""
Playback Manager

Handles video playback (YouTube, streams) using the video MPV pool.
"""
import asyncio
import logging
from typing import Optional

from core.mpv_pools import VideoMPVPool
from core.mpv_controller import MPVController


class PlaybackManager:
    """Manages video playback using the video MPV pool"""

    def __init__(self, video_pool: VideoMPVPool, display_detector, background_manager=None, audio_manager=None):
        """
        Initialize Playback Manager

        Args:
            video_pool: VideoMPVPool instance for video playback
            display_detector: DisplayDetector for resolution detection
            background_manager: Optional BackgroundManager for display control
            audio_manager: Optional AudioManager for stopping audio streams
        """
        self.video_pool = video_pool
        self.display_detector = display_detector
        self.background_manager = background_manager
        self.audio_manager = audio_manager

        # Current playback state
        self.video_controller: Optional[MPVController] = None
        self.current_stream: Optional[str] = None
        self.current_protocol: Optional[str] = None
        self.current_player: Optional[str] = None

    def get_optimal_connector_and_device(self) -> tuple[str, str]:
        """Get optimal DRM connector and device for current display"""
        try:
            connector = self.display_detector.optimal_connector

            # Determine DRM device based on connector
            if connector in self.display_detector.capabilities:
                connector_data = self.display_detector.capabilities[connector]
                if connector_data['item'].startswith('card1-'):
                    return connector, '/dev/dri/card1'
                else:
                    return connector, '/dev/dri/card0'

            return "HDMI-A-1", "/dev/dri/card0"

        except Exception as e:
            logging.warning(f"Failed to get optimal connector: {e}")
            return "HDMI-A-1", "/dev/dri/card0"

    async def play_youtube(self, youtube_url: str, duration: Optional[int] = None, mute: bool = False) -> bool:
        """Play YouTube video using video pool with IPC control"""
        try:
            # Stop any existing playback
            if self.video_controller:
                await self.stop_playback()

            # Stop audio stream if YouTube is playing with audio enabled
            if not mute and self.audio_manager:
                await self.audio_manager.stop_audio_stream()

            # Get optimal display configuration
            optimal_connector, optimal_device = self.get_optimal_connector_and_device()
            width, height, refresh = self.display_detector.get_resolution_for_content_type("youtube")

            # Choose YouTube quality optimized for Pi hardware decoding
            youtube_quality = "bestvideo[vcodec^=avc1][height<=720]+bestaudio/best[height<=720]"

            # Get controller from video pool
            controller = await self.video_pool.get_available_controller()
            if not controller:
                logging.error(f"No available video mpv processes in pool for YouTube: {youtube_url}")
                return False

            logging.info(f"Starting YouTube video using video pool: {youtube_url}")

            # Configure playback settings via IPC
            await controller.send_command(["set", "drm-connector", optimal_connector])
            await controller.send_command(["set", "drm-device", optimal_device])
            await controller.send_command(["set", "fullscreen", "yes"])
            await controller.send_command(["set", "ytdl-format", youtube_quality])

            if mute:
                await controller.send_command(["set", "audio", "no"])
            else:
                await controller.send_command(["set", "audio", "yes"])

            if duration:
                await controller.send_command(["set", "end", str(duration)])

            # Load the YouTube video
            result = await controller.send_command(["loadfile", youtube_url])
            if result.get("error") and result.get("error") != "success":
                error_msg = result.get("error", "Unknown loadfile error")
                logging.error(f"Failed to load YouTube video {youtube_url}: {error_msg}")
                await self.video_pool.release_controller(controller)
                return False

            # Wait for YouTube to fetch metadata and start streaming
            # YouTube videos need more time to initialize than local files
            await asyncio.sleep(3)

            # Verify playback started with multiple checks
            # Check 1: Process is still alive
            process = self.video_pool.processes.get(controller.process_id)
            if not process or process.poll() is not None:
                error_output = ""
                if process:
                    # Try to get stderr output for debugging
                    try:
                        _, stderr = process.communicate(timeout=0.1)
                        if stderr:
                            error_output = f" - mpv error: {stderr.decode('utf-8', errors='ignore').strip()[:200]}"
                    except:
                        pass

                logging.error(f"YouTube playback process died during startup: {youtube_url}{error_output}")
                await self.video_pool.release_controller(controller)
                return False

            # Check 2: Video has filename/title (indicates metadata loaded)
            filename_response = await controller.get_property("filename")
            has_file = filename_response and filename_response.get("data")

            # Check 3: Not in idle state
            idle_response = await controller.get_property("idle-active")
            is_idle = idle_response.get("data", True) if idle_response else True

            # Check 4: Pause state (video should not be paused on start)
            pause_response = await controller.get_property("pause")
            is_paused = pause_response.get("data", True) if pause_response else True

            playback_started = has_file and not is_idle and not is_paused

            if playback_started:
                # Video pool automatically stopped background image - seamless!

                # Set current status
                self.current_stream = f"youtube:{youtube_url}"
                self.current_protocol = "youtube"
                self.current_player = "mpv_video_pool"
                self.video_controller = controller

                logging.info(f"YouTube video started successfully using video pool: {youtube_url}")
                logging.info(f"Using video process ID: {controller.process_id}, muted: {mute}")

                # Auto-return to background after duration if specified
                if duration:
                    asyncio.create_task(self._auto_return_to_background(duration))
                else:
                    asyncio.create_task(self._monitor_youtube_playback())

                return True
            else:
                # Log detailed failure reason
                logging.error(
                    f"YouTube video failed to start: {youtube_url} "
                    f"(has_file={has_file}, is_idle={is_idle}, is_paused={is_paused})"
                )
                await self.video_pool.release_controller(controller)
                if self.background_manager:
                    await self.background_manager.start_static_mode_with_audio_status(show_audio_icon=False)
                return False

        except Exception as e:
            logging.error(f"YouTube playback failed: {e}")
            import traceback
            traceback.print_exc()
            if 'controller' in locals():
                await self.video_pool.release_controller(controller)
            if self.background_manager:
                await self.background_manager.start_static_mode_with_audio_status(show_audio_icon=False)
            return False

    async def stop_playback(self) -> bool:
        """Stop current playback and return to background"""
        try:
            old_protocol = self.current_protocol

            # Release video controller if in use
            if self.video_controller:
                try:
                    await self.video_controller.send_command(["stop"])
                    await self.video_pool.release_controller(self.video_controller)
                    self.video_controller = None
                    logging.info("Released video controller back to pool")
                except Exception as e:
                    logging.error(f"Error releasing video controller: {e}")

            # Show background for seamless transition
            if old_protocol and old_protocol != "background" and self.background_manager:
                await self.background_manager.start_static_mode_with_audio_status(show_audio_icon=False)

            # Clear current playback info
            self.current_stream = None
            self.current_protocol = None
            self.current_player = None

            logging.info("Stopped playback with seamless background transition")

            return True
        except Exception as e:
            logging.error(f"Failed to stop playback: {e}")
            return False

    async def _auto_return_to_background(self, duration: int):
        """Return to background after specified duration"""
        await asyncio.sleep(duration)
        if self.current_protocol == "youtube":
            await self.stop_playback()

    async def _monitor_youtube_playback(self):
        """Monitor YouTube playback and return to background when finished"""
        try:
            # Monitor via video pool process
            if self.video_controller:
                process_id = self.video_controller.process_id
                process = self.video_pool.processes.get(process_id)

                if process:
                    # Check process validity in loop condition to handle cleanup/race conditions
                    while process and process.poll() is None:
                        await asyncio.sleep(1)
                        # Re-fetch process in case pool was modified
                        process = self.video_pool.processes.get(process_id)

                    logging.info("YouTube playback finished, returning to background")
                    if self.current_protocol == "youtube":
                        await self.stop_playback()
        except Exception as e:
            logging.error(f"Error monitoring YouTube playback: {e}")
            if self.background_manager:
                await self.background_manager.start_static_mode_with_audio_status(show_audio_icon=False)

    def get_playback_status(self) -> dict:
        """Get current playback status"""
        is_playing = self.video_controller is not None

        return {
            "is_playing": is_playing,
            "current_stream": self.current_stream if is_playing else None,
            "protocol": self.current_protocol if is_playing else None,
            "player": self.current_player if is_playing else None,
            "process_id": self.video_controller.process_id if is_playing else None
        }
