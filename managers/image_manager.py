"""
Image Manager

Handles image and QR code display on the canvas via the display stack.
Images are saved to static/ directory and pushed to the display stack.
"""
import asyncio
import logging
import os
import base64
import shutil
import qrcode
from pathlib import Path
from datetime import datetime
from typing import Optional

from PIL import Image


class ImageManager:
    """Manages image and QR code display via display stack"""

    def __init__(self, display_detector, display_stack):
        self.display_detector = display_detector
        self.display_stack = display_stack
        self.temp_image_dir = Path("/tmp/stream_images")
        self.temp_image_dir.mkdir(exist_ok=True)
        # Static dir for serving via FastAPI
        self._static_dir = Path(os.path.dirname(os.path.dirname(__file__))) / "static"
        self._static_dir.mkdir(exist_ok=True)

    async def display_image(self, image_path: str, duration: int = 0, background_manager=None) -> bool:
        """Display an image file by pushing it to the display stack"""
        try:
            # Copy image to static/ so it can be served via HTTP
            filename = f"display_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{os.path.basename(image_path)}"
            dest = self._static_dir / filename
            shutil.copy2(image_path, dest)

            await self.display_stack.push(
                "image",
                {"image_url": f"/static/{filename}"},
                duration=duration if duration > 0 else None,
            )

            duration_text = f"{duration}s" if duration > 0 else "indefinitely"
            logging.info(f"Displaying image: {image_path} for {duration_text}")
            return True

        except Exception as e:
            logging.error(f"Failed to display image: {e}")
            return False

    async def save_and_display_image(self, image_data: str, duration: int = 10, background_manager=None) -> bool:
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

    async def display_qr_code(self, content: str, duration: Optional[int] = None, background_manager=None) -> bool:
        """Generate and display a QR code"""
        try:
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4,
            )
            qr.add_data(content)
            qr.make(fit=True)

            img = qr.make_image(fill_color="black", back_color="white")

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"qr_{timestamp}.png"
            qr_path = self._static_dir / filename
            img.save(qr_path)

            logging.info(f"Generated QR code for: {content[:50]}...")

            await self.display_stack.push(
                "qrcode",
                {"image_url": f"/static/{filename}", "qr_content": content},
                duration=duration if duration and duration > 0 else None,
            )

            return True

        except Exception as e:
            logging.error(f"Failed to generate/display QR code: {e}")
            return False

    def stop_image_display(self) -> bool:
        """Stop current image display (legacy compat - uses asyncio)"""
        return True
