"""
Image Manager

Handles image and QR code display on the canvas via the display stack.
Images are written to static/uploads/ and pushed to the display stack. Only
the newest files are kept, plus any file that a stack item still shows.
"""
import asyncio
import base64
import logging
import os
import uuid
from pathlib import Path
from typing import Optional

import qrcode

UPLOAD_URL_PREFIX = "/static/uploads"
# Number of generated files to keep on the SD card
KEEP_FILES = 20


class ImageManager:
    """Manages image and QR code display via display stack"""

    def __init__(self, display_stack, upload_dir: Optional[Path] = None):
        self.display_stack = display_stack
        self.upload_dir = upload_dir or Path(os.path.dirname(os.path.dirname(__file__))) / "static" / "uploads"
        self.upload_dir.mkdir(parents=True, exist_ok=True)

    async def display_image_bytes(self, data: bytes, duration: Optional[int] = None,
                                  suffix: str = ".jpg") -> bool:
        """Store image bytes and push them to the display stack"""
        try:
            url = await asyncio.to_thread(self._store, data, suffix)
            await self.display_stack.push(
                "image", {"image_url": url},
                duration=duration if duration and duration > 0 else None,
            )
            logging.info(f"Displaying image {url} for {duration or 'ever'}s")
            return True
        except Exception as e:
            logging.error(f"Failed to display image: {e}")
            return False

    async def save_and_display_image(self, image_data: str, duration: int = 10) -> bool:
        """Display base64 image data"""
        try:
            data = base64.b64decode(image_data)
        except Exception as e:
            logging.error(f"Invalid base64 image data: {e}")
            return False
        return await self.display_image_bytes(data, duration)

    async def display_qr_code(self, content: str, duration: Optional[int] = None) -> bool:
        """Generate and display a QR code"""
        try:
            url = await asyncio.to_thread(self._make_qr, content)
            logging.info(f"Generated QR code for: {content[:50]}...")
            await self.display_stack.push(
                "qrcode",
                {"image_url": url, "qr_content": content},
                duration=duration if duration and duration > 0 else None,
            )
            return True
        except Exception as e:
            logging.error(f"Failed to generate/display QR code: {e}")
            return False

    def _make_qr(self, content: str) -> str:
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(content)
        qr.make(fit=True)
        filename = f"qr-{uuid.uuid4().hex}.png"
        qr.make_image(fill_color="black", back_color="white").save(self.upload_dir / filename)
        self._prune()
        return f"{UPLOAD_URL_PREFIX}/{filename}"

    def _store(self, data: bytes, suffix: str) -> str:
        suffix = suffix if suffix.startswith(".") and len(suffix) <= 6 else ".jpg"
        filename = f"img-{uuid.uuid4().hex}{suffix.lower()}"
        (self.upload_dir / filename).write_bytes(data)
        self._prune()
        return f"{UPLOAD_URL_PREFIX}/{filename}"

    def _prune(self) -> None:
        """Delete old files. A file that a stack item still shows is kept."""
        in_use = {
            os.path.basename(item["content"].get("image_url", ""))
            for item in self.display_stack.get_stack()
            if isinstance(item.get("content"), dict)
        }
        files = sorted(self.upload_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
        for path in files[KEEP_FILES:]:
            if path.name not in in_use:
                try:
                    path.unlink()
                except OSError as e:
                    logging.warning(f"Could not delete old image {path}: {e}")
