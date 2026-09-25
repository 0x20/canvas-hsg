"""
Background Management for HSG Canvas

The idle screen is the display stack's base layer. This manager owns its
settings (background art, logo/QR overlays) and persists them.
"""
import json
import logging
import os
import uuid
from pathlib import Path
from typing import Optional

from config import CANVAS_DOMAIN


_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Persisted idle-screen overlay settings (logo/QR toggles, QR target, art).
_OVERLAY_SETTINGS_PATH = os.path.join(_BASE_DIR, "overlay_settings.json")
DEFAULT_STATIC_BACKGROUND_URL = "/static/canvas_background_2.png"
# Uploaded background images, served under /static/uploads/
_UPLOAD_DIR = Path(_BASE_DIR) / "static" / "uploads"


def overlay_defaults() -> dict:
    return {
        "background_url": DEFAULT_STATIC_BACKGROUND_URL,
        "show_logo": True,
        "show_qr": True,
        # QR points at the canvas's own URL so a phone can open the control
        # panel; CANVAS_DOMAIN resolves on the LAN (e.g. canvas-zolder.local).
        "qr_url": f"http://{CANVAS_DOMAIN}/",
    }


class BackgroundManager:
    """Manages the idle screen (the display stack's base layer)"""

    def __init__(self, display_stack):
        self.display_stack = display_stack
        self._overlay = self._load_overlay_settings()

    async def show(self) -> None:
        """Remove every item from the stack so the idle screen shows"""
        await self.display_stack.clear()

    async def show_url(self, url: str) -> None:
        """Push a website URL onto the display stack"""
        await self.display_stack.push("website", {"url": url})

    async def set_background_image(self, data: bytes, suffix: str) -> dict:
        """Store an uploaded image and make it the idle-screen background.

        The previous uploaded background is deleted. A new file name each time
        makes browsers load the new image.
        """
        suffix = suffix.lower() if suffix.lower() in (".png", ".jpg", ".jpeg", ".webp", ".gif") else ".png"
        _UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        filename = f"background-{uuid.uuid4().hex}{suffix}"
        (_UPLOAD_DIR / filename).write_bytes(data)
        for old in _UPLOAD_DIR.glob("background-*"):
            if old.name != filename:
                try:
                    old.unlink()
                except OSError as e:
                    logging.warning(f"Could not delete old background {old}: {e}")
        return await self.set_overlay_settings(background_url=f"/static/uploads/{filename}")

    def _load_overlay_settings(self) -> dict:
        settings = overlay_defaults()
        try:
            with open(_OVERLAY_SETTINGS_PATH) as f:
                saved = json.load(f)
            if isinstance(saved, dict):
                for key in settings:
                    if key in saved:
                        settings[key] = saved[key]
        except (OSError, ValueError):
            pass
        return settings

    def _save_overlay_settings(self) -> None:
        try:
            with open(_OVERLAY_SETTINGS_PATH, "w") as f:
                json.dump(self._overlay, f, indent=2)
        except OSError as e:
            logging.warning(f"Could not persist overlay settings: {e}")

    def get_overlay_settings(self) -> dict:
        return dict(self._overlay)

    async def apply_overlay_settings(self) -> None:
        """Push the configured idle background + logo/QR flags into the base layer."""
        await self.display_stack.update_base_content(dict(self._overlay))

    async def set_overlay_settings(self, *, show_logo: Optional[bool] = None,
                                   show_qr: Optional[bool] = None,
                                   qr_url: Optional[str] = None,
                                   background_url: Optional[str] = None) -> dict:
        """Update idle-screen overlays, persist, and re-apply to the base layer."""
        if show_logo is not None:
            self._overlay["show_logo"] = bool(show_logo)
        if show_qr is not None:
            self._overlay["show_qr"] = bool(show_qr)
        if qr_url is not None:
            self._overlay["qr_url"] = qr_url
        if background_url is not None:
            self._overlay["background_url"] = background_url
        self._save_overlay_settings()
        await self.apply_overlay_settings()
        return self.get_overlay_settings()
