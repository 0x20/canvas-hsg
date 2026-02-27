"""
Background Mode Management for HSG Canvas

Thin wrapper around DisplayStack for backward compatibility.
All display switching is now handled by the React app via WebSocket.
"""
import logging
import os
from typing import Optional

from config import DEFAULT_BACKGROUND_PATH


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
