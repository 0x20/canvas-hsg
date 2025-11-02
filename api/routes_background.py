"""
Background Routes

Handles background display mode management.
"""
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import APIRouter, HTTPException, UploadFile, File

if TYPE_CHECKING:
    from background_modes import BackgroundManager

router = APIRouter()


def setup_background_routes(background_manager: 'BackgroundManager') -> APIRouter:
    """
    Setup background routes with dependency injection

    Args:
        background_manager: BackgroundManager instance for background display

    Returns:
        Configured APIRouter
    """

    @router.post("/background/show")
    async def show_background():
        """Show the background display"""
        try:
            # Note: stop_all_visual_content() will be called by unified manager in main.py
            await background_manager.start_static_mode_with_audio_status(show_audio_icon=False)
            return {"message": "Showing background"}
        except Exception as e:
            logging.error(f"Failed to show background: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to show background: {str(e)}")

    @router.post("/background/set")
    async def set_background(file: UploadFile = File(...)):
        """Set a new static background image"""
        # Note: stop_all_visual_content() will be called by unified manager in main.py
        try:
            from config import DEFAULT_BACKGROUND_PATH

            image_data = await file.read()
            temp_dir = Path("/tmp/stream_images")
            temp_dir.mkdir(exist_ok=True)

            # Save the uploaded image
            with open(DEFAULT_BACKGROUND_PATH, "wb") as f:
                f.write(image_data)

            # Restart background to use new image
            await background_manager.stop()
            await background_manager.start_static_mode_with_audio_status(show_audio_icon=False)

            return {"message": "Background image set and scaled to monitor resolution"}

        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to set background: {str(e)}")

    @router.post("/background/mode")
    async def set_background_mode(request: dict):
        """Set background display mode (static only)"""
        logging.info(f"POST /background/mode called with request: {request}")
        # Note: stop_all_visual_content() will be called by unified manager in main.py
        try:
            mode = request.get("mode", "static")
            logging.info(f"Setting background mode to: {mode}")
            if mode != "static":
                raise HTTPException(status_code=400, detail="Invalid mode. Only 'static' mode is supported")

            # Restart background in static mode
            await background_manager.stop()
            await background_manager.start_static_mode_with_audio_status(show_audio_icon=False)

            logging.info(f"Background mode set to: {mode}")
            return {"status": "success", "mode": mode}

        except Exception as e:
            logging.error(f"Failed to set background mode: {e}")
            import traceback
            logging.error(f"Traceback: {traceback.format_exc()}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/background/mode")
    async def get_background_mode():
        """Get current background mode and status"""
        try:
            # Return background manager status
            mode = "static" if background_manager.is_running else "none"
            return {
                "mode": mode,
                "active": background_manager.is_running
            }
        except Exception as e:
            logging.error(f"Failed to get background status: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/background/refresh")
    async def refresh_background():
        """Refresh static background display"""
        # Note: stop_all_visual_content() will be called by unified manager in main.py
        try:
            # Restart static background mode
            await background_manager.stop()
            await background_manager.start_static_mode_with_audio_status(show_audio_icon=False)
            return {"status": "success", "message": "Static background refreshed"}
        except Exception as e:
            logging.error(f"Failed to refresh background: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    return router
