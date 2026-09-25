"""Bluetooth A2DP routes."""
from fastapi import APIRouter, HTTPException


def setup_bluetooth_routes(bluetooth_manager) -> APIRouter:
    router = APIRouter(prefix="/bluetooth", tags=["bluetooth"])

    @router.get("/status")
    async def get_bluetooth_status():
        """Get Bluetooth A2DP connection and playback status"""
        return bluetooth_manager.get_status()

    @router.get("/devices")
    async def list_paired_devices():
        """List all paired Bluetooth devices"""
        devices = await bluetooth_manager.get_paired_devices()
        return {"devices": devices}

    @router.delete("/devices/{address}")
    async def remove_paired_device(address: str):
        """Remove a paired device by MAC address"""
        success = await bluetooth_manager.remove_device(address)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to remove device")
        return {"status": "removed", "address": address}

    @router.post("/discoverable")
    async def set_discoverable(enabled: bool = True):
        """Enable/disable Bluetooth discoverability"""
        success = await bluetooth_manager.set_discoverable(enabled)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to set discoverable")
        return {"discoverable": enabled}

    @router.post("/pairable")
    async def set_pairable(enabled: bool = True):
        """Enable/disable Bluetooth pairing mode"""
        success = await bluetooth_manager.set_pairable(enabled)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to set pairable")
        return {"pairable": enabled}

    @router.post("/disconnect/{address}")
    async def disconnect_device(address: str):
        """Disconnect a currently connected Bluetooth device"""
        success = await bluetooth_manager.disconnect_device(address)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to disconnect device")
        return {"disconnected": True, "address": address}

    return router
