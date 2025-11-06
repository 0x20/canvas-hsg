"""
Image Manager

Handles image and QR code display on the canvas.
"""
import asyncio
import logging
import os
import subprocess
import base64
import qrcode
import io
from pathlib import Path
from datetime import datetime
from typing import Optional

from PIL import Image


class ImageManager:
    """Manages image and QR code display"""

    def __init__(self, display_detector, framebuffer_manager=None, video_pool=None):
        """
        Initialize Image Manager

        Args:
            display_detector: DisplayDetector for resolution detection
            framebuffer_manager: FramebufferManager for image display (deprecated, use video_pool)
            video_pool: Video pool for fullscreen image display
        """
        self.display_detector = display_detector
        self.framebuffer = framebuffer_manager
        self.video_pool = video_pool
        self.image_process: Optional[subprocess.Popen] = None
        self.temp_image_dir = Path("/tmp/stream_images")
        self.temp_image_dir.mkdir(exist_ok=True)
        self._auto_close_task: Optional[asyncio.Task] = None
        self._current_controller = None  # Keep track of controller during image display

    async def display_image(self, image_path: str, duration: int = 0, background_manager=None) -> bool:
        """Display an image file using video pool for true fullscreen"""
        try:
            # Cancel any existing auto-close task
            if self._auto_close_task and not self._auto_close_task.done():
                self._auto_close_task.cancel()

            # Release any previously held controller
            if self._current_controller:
                await self.video_pool.release_controller(self._current_controller)
                self._current_controller = None

            # Use video pool for true fullscreen image display
            if not self.video_pool or not self.video_pool.processes:
                logging.error("Video pool not available for image display")
                return False

            # FORCE get controller - if all busy, get process 1 directly and stop whatever is playing
            controller = await self.video_pool.get_available_controller(retry_with_health_check=False)
            if not controller:
                # No idle controller - forcefully take process 1
                logging.info("No idle controller, forcefully using video pool process 1 for image")
                process_id = 1
                controller = self.video_pool.controllers.get(process_id)
                if not controller:
                    logging.error("Video pool controller 1 not found")
                    return False

                # Stop current playback
                await controller.send_command(["stop"])
                await asyncio.sleep(0.1)

                # Mark as in use
                controller.in_use = True
                self.video_pool.process_status[process_id]["status"] = "busy"

            # Store controller - we'll keep it reserved during image display
            self._current_controller = controller

            # Configure fullscreen display
            await controller.send_command(["set", "fullscreen", "yes"])
            await controller.send_command(["set", "loop-file", "inf" if duration == 0 else "no"])

            # Load and display image
            await controller.send_command(["loadfile", image_path])

            # Wait for image to start loading/displaying
            await asyncio.sleep(0.3)

            duration_text = f"{duration}s" if duration > 0 else "indefinitely"
            logging.info(f"Displaying image via video pool (fullscreen): {image_path} for {duration_text}")

            # Auto-return to background after duration if specified
            if duration > 0 and background_manager:
                self._auto_close_task = asyncio.create_task(
                    self._auto_return_to_background(duration, background_manager)
                )

            return True

        except Exception as e:
            logging.error(f"Failed to display image: {e}")
            import traceback
            traceback.print_exc()
            # Release controller on error
            if self._current_controller:
                await self.video_pool.release_controller(self._current_controller)
                self._current_controller = None
            return False

    async def save_and_display_image(self, image_data: str, duration: int = 10, background_manager=None) -> bool:
        """Save base64 image data and display it"""
        try:
            image_bytes = base64.b64decode(image_data)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            image_path = self.temp_image_dir / f"display_{timestamp}.jpg"

            with open(image_path, "wb") as f:
                f.write(image_bytes)

            return await self.display_image(str(image_path), duration, background_manager)

        except Exception as e:
            logging.error(f"Failed to save and display image: {e}")
            return False

    async def display_qr_code(self, content: str, duration: Optional[int] = None, background_manager=None) -> bool:
        """Generate and display a QR code"""
        try:
            # Generate QR code
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4,
            )
            qr.add_data(content)
            qr.make(fit=True)

            img = qr.make_image(fill_color="black", back_color="white")

            # Save QR code to temp file
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            qr_path = self.temp_image_dir / f"qr_{timestamp}.png"
            img.save(qr_path)

            logging.info(f"Generated QR code for: {content[:50]}...")

            # Display the QR code
            return await self.display_image(str(qr_path), duration if duration else 0, background_manager)

        except Exception as e:
            logging.error(f"Failed to generate/display QR code: {e}")
            return False

    async def _auto_return_to_background(self, duration: int, background_manager):
        """Auto-return to background after specified duration"""
        try:
            await asyncio.sleep(duration)
            logging.info(f"Image duration expired ({duration}s), returning to background")

            # Release the controller before returning to background
            if self._current_controller:
                await self.video_pool.release_controller(self._current_controller)
                self._current_controller = None

            await background_manager.start_static_mode(force_redisplay=True)
        except asyncio.CancelledError:
            logging.info("Auto-return to background cancelled")
        except Exception as e:
            logging.error(f"Failed to return to background: {e}")

    def stop_image_display(self) -> bool:
        """Stop current image display"""
        try:
            if self.image_process and self.image_process.poll() is None:
                self.image_process.terminate()
                try:
                    self.image_process.wait(timeout=2)
                except:
                    self.image_process.kill()
                self.image_process = None
                logging.info("Stopped image display")
                return True
            return False
        except Exception as e:
            logging.error(f"Failed to stop image display: {e}")
            return False
