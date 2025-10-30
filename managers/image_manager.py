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

    def __init__(self, display_detector):
        """
        Initialize Image Manager

        Args:
            display_detector: DisplayDetector for resolution detection
        """
        self.display_detector = display_detector
        self.image_process: Optional[subprocess.Popen] = None
        self.temp_image_dir = Path("/tmp/stream_images")
        self.temp_image_dir.mkdir(exist_ok=True)

    async def display_image(self, image_path: str, duration: int = 0) -> bool:
        """Display an image file"""
        try:
            # Stop any existing image display
            if self.image_process and self.image_process.poll() is None:
                self.image_process.terminate()
                try:
                    self.image_process.wait(timeout=2)
                except:
                    self.image_process.kill()

            # Get display resolution
            width, height, refresh = self.display_detector.get_resolution_for_content_type("image")

            # Use mpv with DRM for image display
            cmd = [
                "sudo", "mpv",
                "--vo=drm",
                "--fs",
                "--quiet",
                f"--loop={'inf' if duration == 0 else '1'}",
                "--no-input-default-bindings",
                "--no-osc",
                image_path
            ]

            logging.info(f"Displaying image: {image_path} for {duration if duration > 0 else 'infinite'} seconds")

            self.image_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                preexec_fn=os.setsid
            )

            # Auto-close after duration if specified
            if duration > 0:
                asyncio.create_task(self._auto_close_image(duration))

            return True

        except Exception as e:
            logging.error(f"Failed to display image: {e}")
            return False

    async def save_and_display_image(self, image_data: str, duration: int = 10) -> bool:
        """Save base64 image data and display it"""
        try:
            image_bytes = base64.b64decode(image_data)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            image_path = self.temp_image_dir / f"display_{timestamp}.jpg"

            with open(image_path, "wb") as f:
                f.write(image_bytes)

            return await self.display_image(str(image_path), duration)

        except Exception as e:
            logging.error(f"Failed to save and display image: {e}")
            return False

    async def display_qr_code(self, content: str, duration: Optional[int] = None) -> bool:
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
            return await self.display_image(str(qr_path), duration if duration else 0)

        except Exception as e:
            logging.error(f"Failed to generate/display QR code: {e}")
            return False

    async def _auto_close_image(self, duration: int):
        """Auto-close image after specified duration"""
        await asyncio.sleep(duration)
        if self.image_process and self.image_process.poll() is None:
            self.image_process.terminate()
            try:
                self.image_process.wait(timeout=2)
            except:
                self.image_process.kill()
            self.image_process = None
            logging.info("Auto-closed image display after duration")

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
