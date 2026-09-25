"""Settings routes: the names the canvas announces."""
from fastapi import APIRouter, HTTPException

from models.request_models import DeviceNameRequest


def setup_settings_routes(device_names) -> APIRouter:
    router = APIRouter(prefix="/settings", tags=["settings"])

    @router.get("/names")
    async def get_names():
        """The Spotify Connect, Bluetooth and Music Assistant names."""
        return device_names.get()

    @router.put("/names")
    async def set_name(request: DeviceNameRequest):
        """Rename one of them. Spotify and Music Assistant restart their service."""
        try:
            await device_names.set(request.kind, request.name)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except RuntimeError as e:
            raise HTTPException(status_code=500, detail=str(e))
        return device_names.get()

    return router
