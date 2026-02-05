"""
Playback Manager

Handles video playback (YouTube, streams) using the video MPV pool.
"""
import asyncio
import logging
from typing import Optional

from managers.mpv_pools import VideoMPVPool
from managers.mpv_controller import MPVController
from config import YOUTUBE_COOKIES_PATH
from utils.drm import get_optimal_connector_and_device as _get_optimal_connector_and_device


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
        return _get_optimal_connector_and_device(self.display_detector)

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
            # IMPORTANT: Prefer AVC1 (H.264) codec - Pi has hardware decoder for this
            # Fall back to other codecs (VP9) if AVC1 not available, but will be choppy
            youtube_quality = "bestvideo[vcodec^=avc1][height<=720]+bestaudio/bestvideo[height<=720]+bestaudio/best"

            # Log warning if we're likely to get VP9 (no hardware acceleration)
            logging.warning(f"YouTube playback: Preferring AVC1 (H.264) for hardware decoding. "
                          f"If video is choppy, it may be using VP9 codec without hardware acceleration.")

            # Get controller from video pool
            controller = await self.video_pool.get_available_controller()
            if not controller:
                logging.error(f"No available video mpv processes in pool for YouTube: {youtube_url}")
                return False

            logging.info(f"Starting YouTube video using video pool: {youtube_url}")

            # Configure playback settings via IPC
            # NOTE: DRM device/connector are already set at mpv launch time and cannot be changed at runtime.
            # However, we still need to set fullscreen and other properties before loadfile.

            # Enable ytdl for YouTube playback (needed since --ytdl flag removed from startup to fix background images)
            await controller.send_command(["set", "ytdl", "yes"])

            # Set YouTube cookies if available
            import os
            if os.path.exists(YOUTUBE_COOKIES_PATH):
                await controller.send_command(["set", "ytdl-raw-options", f"cookies={YOUTUBE_COOKIES_PATH}"])

            await controller.send_command(["set", "fullscreen", "yes"])
            await controller.send_command(["set", "ytdl-format", youtube_quality])

            if mute:
                await controller.send_command(["set", "audio", "no"])
            else:
                await controller.send_command(["set", "audio", "yes"])

            if duration:
                await controller.send_command(["set", "end", str(duration)])

            # Load the YouTube video
            # IMPORTANT: Prefix with ytdl:// to trigger MPV's ytdl_hook
            ytdl_url = f"ytdl://{youtube_url}" if not youtube_url.startswith("ytdl://") else youtube_url
            logging.info(f"Sending loadfile command for: {ytdl_url}")
            result = await controller.send_command(["loadfile", ytdl_url])
            logging.info(f"Loadfile result: {result}")

            if result.get("error") and result.get("error") != "success":
                error_msg = result.get("error", "Unknown loadfile error")
                logging.error(f"Failed to load YouTube video {youtube_url}: {error_msg}")
                await self.video_pool.release_controller(controller)
                return False

            # CRITICAL: Explicitly unpause to start playback in idle mode
            # MPV in idle mode doesn't auto-play after loadfile - we must explicitly unpause
            await controller.send_command(["set_property", "pause", False])

            # Poll for playback to start instead of fixed wait time
            # YouTube needs time for: yt-dlp metadata fetch, stream selection, buffering, decoding
            max_wait_time = 15  # Maximum seconds to wait for playback to start
            poll_interval = 0.5  # Check every 0.5 seconds
            elapsed_time = 0
            playback_started = False

            logging.info(f"Waiting for YouTube video to start (max {max_wait_time}s): {youtube_url}")

            while elapsed_time < max_wait_time:
                await asyncio.sleep(poll_interval)
                elapsed_time += poll_interval

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

                # Check 5: Playback time is progressing (frames actually rendering)
                time_pos_response = await controller.get_property("time-pos")
                time_pos = time_pos_response.get("data") if time_pos_response else None
                has_progressed = time_pos is not None and time_pos > 0.1  # At least 0.1s of video played

                # Check 6: Detect yt-dlp/loading errors early (after 5 seconds of being idle)
                if elapsed_time >= 5.0 and is_idle and not has_file:
                    # Still idle after 5 seconds - likely a yt-dlp error (private video, unavailable, etc.)
                    # Try to read stderr to get a meaningful error message
                    error_msg = None
                    if process and process.stderr:
                        try:
                            # Non-blocking read of stderr
                            import select
                            import os
                            # Set stderr to non-blocking
                            fd = process.stderr.fileno()
                            fl = os.fcntl(fd, os.fcntl.F_GETFL)
                            os.fcntl(fd, os.fcntl.F_SETFL, fl | os.O_NONBLOCK)

                            stderr_data = process.stderr.read()
                            if stderr_data:
                                stderr_text = stderr_data.decode('utf-8', errors='ignore')
                                # Look for common error patterns
                                if 'Private video' in stderr_text or 'Sign in' in stderr_text:
                                    error_msg = "Video is private or requires authentication"
                                elif 'Video unavailable' in stderr_text:
                                    error_msg = "Video is unavailable"
                                elif 'ERROR:' in stderr_text:
                                    # Extract first error line
                                    for line in stderr_text.split('\n'):
                                        if 'ERROR:' in line:
                                            error_msg = line.strip()[:150]
                                            break
                        except Exception as e:
                            logging.debug(f"Could not read stderr: {e}")

                    if error_msg:
                        logging.error(f"YouTube video failed to load: {error_msg}")
                        await self.video_pool.release_controller(controller)
                        if self.background_manager:
                            await self.background_manager.start_static_mode_with_audio_status(show_audio_icon=False)
                        raise RuntimeError(error_msg)

                # Check if playback has actually started AND frames are rendering
                if has_file and not is_idle and not is_paused and has_progressed:
                    playback_started = True
                    logging.info(f"YouTube video playback confirmed with frames rendering after {elapsed_time:.1f}s (time-pos: {time_pos:.2f}s)")

                    # Give it a bit more time to stabilize display pipeline
                    await asyncio.sleep(0.5)
                    break

                # Log detailed state for debugging if we have file but not playing yet
                if has_file and elapsed_time > 2:
                    logging.debug(f"YouTube startup at {elapsed_time:.1f}s: has_file={has_file}, is_idle={is_idle}, is_paused={is_paused}, time_pos={time_pos}")

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
                # Log detailed failure reason with timeout info
                # Get final state for debugging
                final_filename = await controller.get_property("filename")
                final_idle = await controller.get_property("idle-active")
                final_pause = await controller.get_property("pause")

                has_file_final = final_filename and final_filename.get("data")
                is_idle_final = final_idle.get("data", True) if final_idle else True
                is_paused_final = final_pause.get("data", True) if final_pause else True

                logging.error(
                    f"YouTube video failed to start after {elapsed_time:.1f}s timeout: {youtube_url} "
                    f"(has_file={has_file_final}, is_idle={is_idle_final}, is_paused={is_paused_final})"
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
