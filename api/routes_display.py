"""
Display Routes

Handles image and QR code display functionality.
"""
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import APIRouter, HTTPException, UploadFile, File

from models.request_models import QRCodeRequest, ImageDisplayRequest

if TYPE_CHECKING:
    from managers.image_manager import ImageManager

router = APIRouter()


def setup_display_routes(image_manager: 'ImageManager') -> APIRouter:
    """
    Setup display routes with dependency injection

    Args:
        image_manager: ImageManager instance for image/QR display

    Returns:
        Configured APIRouter
    """

    @router.post("/display/qrcode")
    async def display_qr_code(request: QRCodeRequest):
        """Generate and display a QR code with text overlay"""
        # Note: stop_all_visual_content() will be called by unified manager in main.py
        success = await image_manager.display_qr_code(request.content, request.duration)
        if success:
            duration_text = f" for {request.duration}s" if request.duration else " (forever)"
            return {"message": f"Displaying QR code for '{request.content}'{duration_text}"}
        else:
            raise HTTPException(status_code=500, detail="Failed to generate and display QR code")

    @router.post("/display/image")
    async def display_image_endpoint(file: UploadFile = File(...), duration: int = 10):
        """Upload and display an image on screen"""
        try:
            image_data = await file.read()
            temp_dir = Path("/tmp/stream_images")
            temp_dir.mkdir(exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            image_path = temp_dir / f"upload_{timestamp}_{file.filename}"

            with open(image_path, "wb") as f:
                f.write(image_data)

            success = await image_manager.display_image(str(image_path), duration)

            if success:
                return {"message": f"Displaying image for {duration} seconds", "path": str(image_path)}
            else:
                raise HTTPException(status_code=500, detail="Failed to display image")

        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to upload image: {str(e)}")

    @router.post("/display/image/base64")
    async def display_image_base64(request: ImageDisplayRequest):
        """Display a base64 encoded image"""
        success = await image_manager.save_and_display_image(request.image_data, request.duration)
        if success:
            return {"message": f"Displaying image for {request.duration} seconds"}
        else:
            raise HTTPException(status_code=500, detail="Failed to display image")

    return router
