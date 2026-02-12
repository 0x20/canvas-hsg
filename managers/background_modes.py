"""
Background Mode Management for HSG Canvas
Handles static background image display with scaling and centering.
"""

import asyncio
import os
import time
import logging
from pathlib import Path
from typing import Optional, Any
from PIL import Image

from config import DEFAULT_BACKGROUND_PATH


class BackgroundManager:
    """Manages static background image display"""

    def __init__(self, display_detector, framebuffer_manager, video_pool=None, chromium_manager=None):
        self.display_detector = display_detector
        self.framebuffer = framebuffer_manager
        self.video_pool = video_pool
        self.chromium_manager = chromium_manager

        # Current state
        self.is_running = False
        self.current_mode = None  # "static", "now_playing_web", "now_playing_video"
        
        # Static background image path - set to canvas_background.png by default
        self.static_background_image = DEFAULT_BACKGROUND_PATH
        
        # Verify the default background exists
        if not os.path.exists(self.static_background_image):
            logging.warning(f"Default background image not found: {self.static_background_image}")
            self.static_background_image = None
        
        # Paths
        self.temp_dir = Path("/tmp/stream_images")
        self.temp_dir.mkdir(exist_ok=True)
        self.current_background_path = self.temp_dir / "current_background.png"
    
    async def start_static_mode(self, force_redisplay: bool = False) -> bool:
        """Start static background display

        Args:
            force_redisplay: If True, redisplay even if already running
        """
        try:
            if self.is_running and self.current_mode == "static" and not force_redisplay:
                return True

            # Stop any current display (Chromium or MPV)
            await self._stop_current_display()

            logging.info("Starting static background mode")
            await self._start_static_mode()
            self.is_running = True
            self.current_mode = "static"
            return True

        except Exception as e:
            logging.error(f"Failed to start static background mode: {e}")
            return False
    
    async def start_static_mode_with_audio_status(self, show_audio_icon: bool = False) -> bool:
        """Start static background mode with audio status icon"""
        try:
            await self.stop()
            
            logging.info(f"Starting static background mode (audio icon: {show_audio_icon})")
            await self._start_static_mode(show_audio_icon=show_audio_icon)
            self.is_running = True
            return True
            
        except Exception as e:
            logging.error(f"Failed to start static background mode: {e}")
            return False
    
    async def _start_static_mode(self, show_audio_icon: bool = False) -> None:
        """Start static background mode"""
        await self._create_static_background(show_audio_icon=show_audio_icon)
        await self._display_current_background()
    
    async def _create_static_background(self, show_audio_icon: bool = False) -> None:
        """Scale and display static background image to monitor resolution"""
        try:
            # Get optimal resolution
            display_config = self.display_detector.get_optimal_framebuffer_config()
            width, height = display_config['width'], display_config['height']
            
            if not self.static_background_image or not os.path.exists(self.static_background_image):
                # Create a simple fallback background if no image is set
                img = Image.new('RGB', (width, height), (20, 20, 30))
                logging.warning(f"No background image set, using fallback color: {width}x{height}")
            else:
                # Load and scale the static background image
                img = self._scale_image_to_resolution(self.static_background_image, width, height)
                logging.info(f"Scaled background image to: {width}x{height}")
            
            # Save scaled background with fast compression for quicker loading
            # compress_level=1 (fastest) instead of default 6 - trades file size for speed
            img.save(str(self.current_background_path), compress_level=1)
            
        except Exception as e:
            logging.error(f"Failed to create static background: {e}")
            # Create fallback background
            display_config = self.display_detector.get_optimal_framebuffer_config()
            width, height = display_config['width'], display_config['height']
            img = Image.new('RGB', (width, height), (20, 20, 30))
            img.save(str(self.current_background_path))
    
    async def _display_current_background(self) -> None:
        """Display the current background image using video pool mpv (seamless!)"""
        if not self.current_background_path.exists():
            raise RuntimeError("No background image to display")

        # Use video pool to display background - seamless content switching!
        if not self.video_pool or not self.video_pool.processes:
            raise RuntimeError("Video pool not available for background display")

        # Get idle controller from video pool
        controller = await self.video_pool.get_available_controller()
        if not controller:
            raise RuntimeError("No available video pool controller for background")

        # Set loop-file to infinite (mpv already started with --fs so fullscreen is automatic)
        await controller.send_command(["set", "loop-file", "inf"])

        # Load background image - will display fullscreen instantly
        # Note: mpv is started with --no-ytdl to prevent yt-dlp from probing the image file
        await controller.send_command(["loadfile", str(self.current_background_path)])

        # Release controller back to pool (it keeps playing the background)
        await self.video_pool.release_controller(controller)

        logging.info("Background displayed using video pool (seamless content switching)")

    def set_background_image(self, image_path: str) -> bool:
        """Set the static background image path"""
        try:
            if not os.path.exists(image_path):
                logging.error(f"Background image not found: {image_path}")
                return False
            
            # Verify it's a valid image
            with Image.open(image_path) as img:
                img.verify()
            
            self.static_background_image = image_path
            logging.info(f"Set background image: {image_path}")
            return True
            
        except Exception as e:
            logging.error(f"Invalid background image {image_path}: {e}")
            return False
    
    def _scale_image_to_resolution(self, image_path: str, target_width: int, target_height: int) -> Image.Image:
        """Scale image to target resolution while preserving aspect ratio"""
        try:
            with Image.open(image_path) as img:
                # Convert to RGB if necessary
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                
                # Get original dimensions
                orig_width, orig_height = img.size
                
                logging.info(f"Original image: {orig_width}x{orig_height}, Target: {target_width}x{target_height}")
                
                # If image already matches target resolution exactly, return as-is
                if orig_width == target_width and orig_height == target_height:
                    logging.info("Image already matches target resolution - no scaling needed")
                    return img.copy()
                
                # Calculate scaling factor to fit within target dimensions
                width_ratio = target_width / orig_width
                height_ratio = target_height / orig_height
                scale_factor = min(width_ratio, height_ratio)
                
                # Calculate new dimensions
                new_width = int(orig_width * scale_factor)
                new_height = int(orig_height * scale_factor)
                
                logging.info(f"Scale factor: {scale_factor:.3f}, New size: {new_width}x{new_height}")
                
                # If scale factor is 1 and dimensions match, no need for canvas
                if scale_factor == 1.0 and new_width == target_width and new_height == target_height:
                    logging.info("Perfect 1:1 scale - returning original")
                    return img.copy()
                
                # Resize image
                scaled_img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                
                # Create target canvas and center the scaled image
                canvas = Image.new('RGB', (target_width, target_height), (0, 0, 0))
                x_offset = (target_width - new_width) // 2
                y_offset = (target_height - new_height) // 2
                canvas.paste(scaled_img, (x_offset, y_offset))
                
                logging.info(f"Scaled and centered: offset ({x_offset}, {y_offset})")
                return canvas
                
        except Exception as e:
            logging.error(f"Failed to scale image {image_path}: {e}")
            # Return black canvas as fallback
            return Image.new('RGB', (target_width, target_height), (0, 0, 0))
    
    async def _stop_current_display(self) -> None:
        """Stop current display mode (Chromium or MPV) without destroying pools"""
        if self.current_mode == "now_playing_web" and self.chromium_manager:
            logging.info("Stopping Chromium display")
            await self.chromium_manager.stop()

            # Restart video pool after Chromium stops (to reclaim DRM)
            logging.info("Restarting video pool after Chromium shutdown")
            if self.video_pool:
                self.video_pool.suspended = False
                await self.video_pool.initialize()
        elif self.current_mode in ("static", "now_playing_video"):
            # MPV-based display - stop playback via 'stop' command
            if self.video_pool:
                controller = await self.video_pool.get_available_controller()
                if controller:
                    try:
                        # Send stop command to MPV
                        await controller.send_command(["stop"])
                    except Exception as e:
                        logging.debug(f"Error stopping MPV playback: {e}")
                    finally:
                        await self.video_pool.release_controller(controller)

        self.current_mode = None
        self.is_running = False

    async def start_now_playing_web_mode(self) -> bool:
        """Start web-based now-playing display via Chromium kiosk mode

        Returns:
            True if successfully started, False otherwise
        """
        if not self.chromium_manager:
            logging.error("ChromiumManager not available - cannot start web mode")
            return False

        # If already in web mode, don't restart - WebSocket will update the page
        if self.current_mode == "now_playing_web" and self.chromium_manager.is_running():
            logging.debug("Web-based now-playing mode already active - skipping restart")
            return True

        try:
            # Stop current display (preserves video pool for later use)
            await self._stop_current_display()

            # CRITICAL: Stop video pool to free DRM device for Chromium
            # Chromium needs exclusive DRM access, can't share with MPV
            logging.info("Stopping video pool to free DRM for Chromium (suspended)")
            if self.video_pool:
                await self.video_pool.cleanup(suspend=True)

            # Give DRM time to be released
            import asyncio
            await asyncio.sleep(0.5)

            # Point to Vite dev server for React app with hot reload
            # Start directly on now-playing path
            url = "http://127.0.0.1:5173/now-playing"
            logging.info(f"Using URL for Chromium: {url}")

            logging.info(f"Starting web-based now-playing mode: {url}")

            # Pass video pool reference to ChromiumManager so it can restart it later
            self.chromium_manager.video_pool = self.video_pool

            # Launch Chromium kiosk pointing to /now-playing
            success = await self.chromium_manager.start_kiosk(url)

            if success:
                self.current_mode = "now_playing_web"
                self.is_running = True
                logging.info("Web-based now-playing mode started successfully")
                return True
            else:
                logging.error("Failed to start Chromium kiosk mode")
                # Restart video pool since Chromium failed
                if self.video_pool:
                    self.video_pool.suspended = False
                    await self.video_pool.initialize()
                return False

        except Exception as e:
            logging.error(f"Failed to start web-based now-playing mode: {e}")
            # Restart video pool on error
            if self.video_pool:
                self.video_pool.suspended = False
                await self.video_pool.initialize()
            return False

    async def switch_to_now_playing(self) -> bool:
        """Switch Chromium to now-playing view without restarting

        If Chromium is not running, starts it. If it's running, just navigates to the URL.

        Returns:
            True if successful, False otherwise
        """
        if not self.chromium_manager:
            logging.error("ChromiumManager not available")
            return False

        try:
            # URL for Vite dev server - React router will handle path
            url = "http://127.0.0.1:5173/now-playing"

            # Restart Chromium with new URL (navigation via xdotool is unreliable)
            logging.info("Restarting Chromium for now-playing view")
            if self.chromium_manager.is_running():
                await self.chromium_manager.stop()

            # Stop video pool to free DRM (suspended so health monitor won't restart it)
            if self.video_pool:
                await self.video_pool.cleanup(suspend=True)
            await asyncio.sleep(0.5)

            self.chromium_manager.video_pool = self.video_pool
            success = await self.chromium_manager.start_kiosk(url)

            if success:
                self.current_mode = "now_playing_web"
                self.is_running = True
                return True
            else:
                if self.video_pool:
                    self.video_pool.suspended = False
                    await self.video_pool.initialize()
                return False

        except Exception as e:
            logging.error(f"Failed to switch to now-playing: {e}")
            return False

    async def switch_to_static(self) -> bool:
        """Switch Chromium to static background view without restarting

        If Chromium is not running, starts it. If it's running, just navigates to the URL.

        Returns:
            True if successful, False otherwise
        """
        if not self.chromium_manager:
            logging.error("ChromiumManager not available")
            return False

        try:
            # URL for Vite dev server - React router will show static background
            url = "http://127.0.0.1:5173/"

            # Restart Chromium with new URL (navigation via xdotool is unreliable)
            logging.info("Restarting Chromium for static background view")
            if self.chromium_manager.is_running():
                await self.chromium_manager.stop()

            # Stop video pool to free DRM (suspended so health monitor won't restart it)
            if self.video_pool:
                await self.video_pool.cleanup(suspend=True)
            await asyncio.sleep(0.5)

            # Start Chromium with static background URL
            self.chromium_manager.video_pool = self.video_pool
            success = await self.chromium_manager.start_kiosk(url)

            if success:
                self.current_mode = "static_web"
                self.is_running = True
                return True
            else:
                # Restart video pool on failure
                if self.video_pool:
                    self.video_pool.suspended = False
                    await self.video_pool.initialize()
                return False

        except Exception as e:
            logging.error(f"Failed to switch to static: {e}")
            if self.video_pool:
                self.video_pool.suspended = False
            return False

    async def stop(self) -> None:
        """Stop background display (video pool handles this automatically)"""
        await self._stop_current_display()
        logging.info("Background manager stopped")
    
    def is_active(self) -> bool:
        """Check if background display is active"""
        return self.is_running
    
    def get_status(self) -> dict:
        """Get current status information"""
        return {
            "mode": "static",
            "is_running": self.is_running,
            "background_image": self.static_background_image
        }