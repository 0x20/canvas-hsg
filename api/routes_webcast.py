"""
Webcast Routes

Handles website webcasting with auto-scroll functionality.
"""
import logging
from typing import TYPE_CHECKING

from fastapi import APIRouter, HTTPException, Request

if TYPE_CHECKING:
    from webcast_manager import WebcastManager, WebcastConfig

router = APIRouter()


def setup_webcast_routes(webcast_manager: 'WebcastManager') -> APIRouter:
    """
    Setup webcast routes with dependency injection

    Args:
        webcast_manager: WebcastManager instance for website webcasting

    Returns:
        Configured APIRouter
    """

    @router.post("/webcast/start")
    async def start_webcast(request: Request):
        """Start webcasting a website with auto-scroll"""
        # Note: stop_all_visual_content() will be called by unified manager in main.py
        try:
            from webcast_manager import WebcastConfig

            data = await request.json()

            # Create webcast configuration
            config = WebcastConfig(
                url=data.get("url"),
                viewport_width=data.get("viewport_width", 1920),
                viewport_height=data.get("viewport_height", 1080),
                scroll_delay=data.get("scroll_delay", 5.0),
                scroll_percentage=data.get("scroll_percentage", 30.0),
                overlap_percentage=data.get("overlap_percentage", 5.0),
                loop_count=data.get("loop_count", 3),
                zoom_level=data.get("zoom_level", 1.0),
                wait_for_load=data.get("wait_for_load", 3.0),
                screenshot_path=data.get("screenshot_path", "/tmp/webcast_screenshot.png")
            )

            result = await webcast_manager.start_webcast(config)

            # Note: Automatic screenshot display will be handled by unified manager in main.py

            return result

        except Exception as e:
            logging.error(f"Failed to start webcast: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/webcast/stop")
    async def stop_webcast():
        """Stop the current webcast"""
        try:
            result = await webcast_manager.stop_webcast()
            return result
        except Exception as e:
            logging.error(f"Failed to stop webcast: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/webcast/status")
    async def get_webcast_status():
        """Get current webcast status"""
        try:
            return await webcast_manager.get_status()
        except Exception as e:
            logging.error(f"Failed to get webcast status: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/webcast/config")
    async def update_webcast_config(request: Request):
        """Update webcast configuration"""
        try:
            data = await request.json()
            result = await webcast_manager.update_config(data)
            return result
        except Exception as e:
            logging.error(f"Failed to update webcast config: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/webcast/scroll")
    async def manual_webcast_scroll(request: Request):
        """Manually scroll the webcast"""
        try:
            data = await request.json()
            direction = data.get("direction", "down")
            amount = data.get("amount")

            result = await webcast_manager.manual_scroll(direction, amount)
            return result
        except Exception as e:
            logging.error(f"Failed to scroll webcast: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/webcast/jump")
    async def jump_webcast_position(request: Request):
        """Jump to a specific position in the webcast"""
        try:
            data = await request.json()
            position_percent = data.get("position_percent", 0)

            result = await webcast_manager.jump_to_position(position_percent)
            return result
        except Exception as e:
            logging.error(f"Failed to jump webcast: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    return router
