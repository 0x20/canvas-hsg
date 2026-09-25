"""Display stack, image/QR, idle-screen and kiosk browser routes."""
import os

from fastapi import APIRouter, File, HTTPException, UploadFile

from models.request_models import (
    BackgroundModeRequest,
    DisplayPushRequest,
    ImageDisplayRequest,
    QRCodeRequest,
    StaticOverlayRequest,
    VideoDisplayRequest,
    WebsiteDisplayRequest,
)


def setup_display_routes(display_stack, image_manager, background_manager, chromium_manager=None) -> APIRouter:
    router = APIRouter()

    # ── Images and QR codes ──────────────────────────────────────────

    @router.post("/display/qrcode")
    async def display_qr_code(request: QRCodeRequest):
        """Generate and display a QR code with text overlay"""
        if not await image_manager.display_qr_code(request.content, request.duration):
            raise HTTPException(status_code=500, detail="Failed to generate and display QR code")
        duration_text = f" for {request.duration}s" if request.duration else " (forever)"
        return {"message": f"Displaying QR code for '{request.content}'{duration_text}"}

    @router.post("/display/image")
    async def display_image_upload(file: UploadFile = File(...), duration: int = 10):
        """Upload and display an image on screen"""
        suffix = os.path.splitext(file.filename or "")[1] or ".jpg"
        if not await image_manager.display_image_bytes(await file.read(), duration, suffix):
            raise HTTPException(status_code=500, detail="Failed to display image")
        return {"message": f"Displaying image for {duration} seconds"}

    @router.post("/display/image/base64")
    async def display_image_base64(request: ImageDisplayRequest):
        """Display a base64 encoded image"""
        if not await image_manager.save_and_display_image(request.image_data, request.duration):
            raise HTTPException(status_code=500, detail="Failed to display image")
        return {"message": f"Displaying image for {request.duration} seconds"}

    # ── Display stack ────────────────────────────────────────────────

    @router.post("/display/push")
    async def push_display_item(request: DisplayPushRequest):
        """Push a generic display item onto the stack"""
        item = await display_stack.push(
            request.type,
            request.content,
            duration=request.duration,
            item_id=request.item_id,
        )
        return {"message": f"Pushed {request.type} to display stack", "item": item.to_dict()}

    @router.post("/display/website")
    async def push_website(request: WebsiteDisplayRequest):
        """Push a website URL onto the display stack"""
        content = {"url": request.url}
        if request.zoom:
            content["zoom"] = request.zoom
        item = await display_stack.push("website", content, duration=request.duration)
        return {"message": f"Displaying website: {request.url}", "item": item.to_dict()}

    @router.post("/display/video")
    async def push_video(request: VideoDisplayRequest):
        """Push a video URL onto the display stack"""
        content = {"video_url": request.video_url}
        if request.mute is not None:
            content["mute"] = request.mute
        item = await display_stack.push("video", content, duration=request.duration)
        return {"message": f"Displaying video: {request.video_url}", "item": item.to_dict()}

    @router.get("/display/stack")
    async def get_display_stack():
        """Get the current display stack state"""
        return {
            "current": display_stack.current.to_dict(),
            "stack": display_stack.get_stack(),
        }

    @router.delete("/display/clear")
    async def clear_display_stack():
        """Clear all items from the display stack (back to static background)"""
        await display_stack.clear()
        return {"message": "Display stack cleared", "current": display_stack.current.to_dict()}

    @router.post("/display/navigate")
    async def navigate_display(request: dict):
        """Show the idle screen or a website.

        Body: {"url": "static"} or {"url": "<http(s) URL>"}
        """
        url = request.get("url", "static")
        if url == "static":
            await background_manager.show()
        elif url.startswith(("http://", "https://")):
            await background_manager.show_url(url)
        else:
            raise HTTPException(status_code=400,
                                detail=f"Invalid URL: {url}. Use 'static' or a full http(s) URL.")
        return {"status": "success", "url": url}

    # ── Idle screen ──────────────────────────────────────────────────

    @router.post("/background/show")
    @router.post("/background/refresh")
    async def show_background():
        """Show the idle screen (clears the display stack)"""
        await background_manager.show()
        return {"status": "success", "message": "Showing background"}

    @router.post("/background/mode")
    async def set_background_mode(request: BackgroundModeRequest):
        """Set background display mode. Only 'static' exists."""
        if request.mode != "static":
            raise HTTPException(status_code=400, detail="Invalid mode. Only 'static' mode is supported")
        await background_manager.show()
        return {"status": "success", "mode": request.mode}

    @router.get("/background/mode")
    async def get_background_mode():
        """The idle screen is always the static background."""
        return {"mode": "static", "active": True}

    @router.post("/background/set")
    async def set_background(file: UploadFile = File(...)):
        """Set a new idle-screen background image"""
        suffix = os.path.splitext(file.filename or "")[1]
        settings = await background_manager.set_background_image(await file.read(), suffix)
        return {"message": "Background image set", "background_url": settings["background_url"]}

    @router.get("/background/overlays")
    async def get_background_overlays():
        """Current idle-screen overlay settings (logo/QR toggles + QR target)."""
        return background_manager.get_overlay_settings()

    @router.post("/background/overlays")
    async def set_background_overlays(request: StaticOverlayRequest):
        """Toggle the idle-screen logo/QR overlays (persisted across restarts)."""
        return await background_manager.set_overlay_settings(
            show_logo=request.show_logo,
            show_qr=request.show_qr,
            qr_url=request.qr_url,
            background_url=request.background_url,
        )

    # ── Kiosk browser (Chrome DevTools Protocol) ─────────────────────

    @router.post("/display/reload")
    async def reload_chromium():
        """Reload the Chromium kiosk page via Chrome DevTools Protocol"""
        if not chromium_manager:
            raise HTTPException(status_code=503, detail="Chromium manager not available")
        if not await chromium_manager.reload_page():
            raise HTTPException(status_code=500, detail="Failed to reload page")
        return {"message": "Page reloaded"}

    @router.post("/display/kiosk/navigate")
    async def navigate_chromium(url: str):
        """Navigate the Chromium kiosk to a new URL via Chrome DevTools Protocol"""
        if not chromium_manager:
            raise HTTPException(status_code=503, detail="Chromium manager not available")
        if not await chromium_manager.navigate(url):
            raise HTTPException(status_code=500, detail="Failed to navigate")
        return {"message": f"Navigated to {url}"}

    # Must stay last: it matches every /display/<id> path
    @router.delete("/display/{item_id}")
    async def remove_display_item(item_id: str):
        """Remove a specific item from the display stack"""
        if not await display_stack.remove(item_id):
            raise HTTPException(status_code=404, detail=f"Item {item_id} not found in stack")
        return {"message": f"Removed item {item_id}", "current": display_stack.current.to_dict()}

    return router
