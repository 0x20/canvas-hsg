"""
HDMI-CEC Routes

Handles HDMI-CEC TV/monitor control endpoints.
"""
from typing import TYPE_CHECKING

from fastapi import APIRouter, HTTPException

if TYPE_CHECKING:
    # HDMICECManager is defined in srsserver.py, will need to be extracted
    pass

router = APIRouter()


def setup_cec_routes(cec_manager) -> APIRouter:
    """
    Setup HDMI-CEC routes with dependency injection

    Args:
        cec_manager: HDMICECManager instance for TV control

    Returns:
        Configured APIRouter
    """

    @router.post("/cec/tv/power-on")
    async def power_on_tv():
        """Turn on TV/monitor via HDMI-CEC"""
        result = await cec_manager.power_on_tv()
        if result["success"]:
            return {"message": result["message"], "tv_address": result["tv_address"]}
        else:
            raise HTTPException(status_code=500, detail=result["message"])

    @router.post("/cec/tv/power-off")
    async def power_off_tv():
        """Put TV/monitor in standby via HDMI-CEC"""
        result = await cec_manager.power_off_tv()
        if result["success"]:
            return {"message": result["message"], "tv_address": result["tv_address"]}
        else:
            raise HTTPException(status_code=500, detail=result["message"])

    @router.get("/cec/status")
    async def get_cec_status():
        """Get HDMI-CEC status and TV power state"""
        status = cec_manager.get_status()

        # Also get TV power status if CEC is available
        if status["available"]:
            power_result = await cec_manager.get_tv_power_status()
            status["tv_power"] = power_result
        else:
            status["tv_power"] = {"success": False, "power_status": "unavailable"}

        return status

    @router.post("/cec/scan")
    async def scan_cec_devices():
        """Scan for HDMI-CEC devices"""
        result = await cec_manager.scan_devices()
        return result

    return router
