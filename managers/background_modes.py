"""
Background Mode Management for HSG Canvas

Thin wrapper around DisplayStack for backward compatibility.
All display switching is now handled by the React app via WebSocket.
"""
import json
import logging
import os
from typing import Optional

from config import DEFAULT_BACKGROUND_PATH, CANVAS_DOMAIN


# Persisted idle-screen overlay settings (logo/QR toggles, QR target, art).
_OVERLAY_SETTINGS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "overlay_settings.json"
)
DEFAULT_STATIC_BACKGROUND_URL = "/static/canvas_background_2.png"


class BackgroundManager:
    """Manages background display via display stack"""

    def __init__(self, display_detector, display_stack):
        self.display_detector = display_detector
        self.display_stack = display_stack

        # Current state (kept for backward compat with status checks)
        self.is_running = True
        self.current_mode = "static_web"

        # Static background image path
        self.static_background_image = DEFAULT_BACKGROUND_PATH
        if not os.path.exists(self.static_background_image):
            logging.warning(f"Default background image not found: {self.static_background_image}")
            self.static_background_image = None

        # Idle-screen overlay settings (logo + QR), persisted across restarts.
        self._overlay = self._load_overlay_settings()

    async def start_static_mode(self, force_redisplay: bool = False) -> bool:
        """Clear stack to show static background"""
        try:
            await self.display_stack.clear()
            self.current_mode = "static_web"
            self.is_running = True
            return True
        except Exception as e:
            logging.error(f"Failed to start static background mode: {e}")
            return False

    async def start_static_mode_with_audio_status(self, show_audio_icon: bool = False) -> bool:
        """Start static background mode (audio icon is now handled by React)"""
        return await self.start_static_mode()

    async def switch_to_now_playing(self) -> bool:
        """Push Spotify now-playing onto the display stack"""
        try:
            await self.display_stack.push("spotify", {}, item_id="spotify")
            self.current_mode = "now_playing_web"
            self.is_running = True
            return True
        except Exception as e:
            logging.error(f"Failed to switch to now-playing: {e}")
            return False

    async def switch_to_static(self) -> bool:
        """Clear stack to show static background"""
        return await self.start_static_mode()

    async def switch_to_url(self, url: str) -> bool:
        """Push a website URL onto the display stack"""
        try:
            await self.display_stack.push("website", {"url": url})
            self.current_mode = "custom_web"
            self.is_running = True
            return True
        except Exception as e:
            logging.error(f"Failed to switch to URL {url}: {e}")
            return False

    def set_background_image(self, image_path: str) -> bool:
        """Set the static background image path"""
        try:
            if not os.path.exists(image_path):
                logging.error(f"Background image not found: {image_path}")
                return False
            self.static_background_image = image_path
            logging.info(f"Set background image: {image_path}")
            return True
        except Exception as e:
            logging.error(f"Invalid background image {image_path}: {e}")
            return False

    async def set_background_image_async(self, image_path: str) -> bool:
        """Set background image and update the display stack base"""
        if self.set_background_image(image_path):
            await self.display_stack.update_base_content({
                "background_url": f"/static/{os.path.basename(image_path)}"
            })
            return True
        return False

    def _overlay_defaults(self) -> dict:
        return {
            "background_url": DEFAULT_STATIC_BACKGROUND_URL,
            "show_logo": True,
            "show_qr": True,
            # QR points at the canvas's own URL so a phone can open the control
            # panel; CANVAS_DOMAIN resolves on the LAN (e.g. canvas-zolder.local).
            "qr_url": f"http://{CANVAS_DOMAIN}/",
        }

    def _load_overlay_settings(self) -> dict:
        settings = self._overlay_defaults()
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

    async def stop(self) -> None:
        """Stop background display"""
        await self.display_stack.clear()
        self.current_mode = None
        self.is_running = False
        logging.info("Background manager stopped")

    def is_active(self) -> bool:
        return self.is_running

    def get_status(self) -> dict:
        return {
            "mode": self.current_mode or "static",
            "is_running": self.is_running,
            "background_image": self.static_background_image,
            "display_stack": self.display_stack.get_stack()
        }
