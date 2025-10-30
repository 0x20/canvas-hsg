"""
Screen Streaming Routes

Handles screen capture and streaming to SRS server.
"""
from typing import TYPE_CHECKING

from fastapi import APIRouter, HTTPException

if TYPE_CHECKING:
    from managers.screen_stream_manager import ScreenStreamManager

router = APIRouter()


def setup_screen_routes(screen_stream_manager: 'ScreenStreamManager') -> APIRouter:
    """
    Setup screen streaming routes with dependency injection

    Args:
        screen_stream_manager: ScreenStreamManager instance for screen capture

    Returns:
        Configured APIRouter
    """

    @router.post("/screen-stream/{stream_key}/start")
    async def start_screen_stream(stream_key: str, protocol: str = "rtmp"):
        """Start streaming the display output"""
        success = await screen_stream_manager.start_screen_stream(stream_key, protocol)
        if success:
            return {"message": f"Screen streaming started: {stream_key} via {protocol.upper()}"}
        else:
            raise HTTPException(status_code=500, detail=f"Failed to start screen streaming via {protocol}")

    @router.delete("/screen-stream/stop")
    async def stop_screen_stream():
        """Stop screen streaming"""
        success = await screen_stream_manager.stop_screen_stream()
        if success:
            return {"message": "Screen streaming stopped"}
        else:
            raise HTTPException(status_code=404, detail="No active screen stream")

    @router.get("/screen-stream/status")
    async def get_screen_stream_status():
        """Get screen streaming status"""
        return screen_stream_manager.get_screen_stream_info()

    @router.get("/screen-stream/capabilities")
    async def get_screen_capture_capabilities():
        """
        Check FFmpeg and DRM capabilities for screen capture

        Note: This is a placeholder - actual implementation depends on
        access to display_detector and other system components
        """
        # This will be implemented when we have access to display_detector
        # and can check FFmpeg capabilities
        return {
            "message": "Capability detection will be implemented in main.py",
            "methods_supported": ["framebuffer", "kmsgrab"]
        }

    return router
