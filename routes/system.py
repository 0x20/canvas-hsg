"""Health, status, media source and device description routes."""
import os
from datetime import datetime

from fastapi import APIRouter
from fastapi.responses import Response

from config import APP_VERSION, DEVICE_NAME
from utils.media_sources import load_media_sources


def setup_system_routes(display_detector=None, station_store=None) -> APIRouter:
    router = APIRouter()

    @router.get("/health")
    async def health_check():
        """Health check endpoint"""
        return {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "version": APP_VERSION,
            "architecture": "display-stack"
        }

    @router.get("/status")
    async def get_status():
        """Get overall system status"""
        return {
            "timestamp": datetime.now().isoformat(),
            "engine": "browser",
            "display": "react",
            "audio": "browser-websocket",
        }

    @router.get("/diagnostics")
    async def get_diagnostics():
        """
        Get comprehensive system diagnostics

        Note: Full diagnostics require access to display_detector and other system components.
        """
        diag = {
            "timestamp": datetime.now().isoformat(),
            "user": os.getenv('USER', 'unknown'),
            "display_env": os.getenv('DISPLAY', 'not_set'),
            "audio_device": os.getenv('AUDIO_DEVICE', 'not_set')
        }

        if display_detector:
            # Add display information when available
            diag["display"] = {
                "optimal_connector": getattr(display_detector, 'optimal_connector', 'unknown'),
                "capabilities_detected": len(getattr(display_detector, 'capabilities', {}))
            }

        return diag

    @router.get("/media-sources")
    async def get_media_sources():
        """Get configured media sources for the web interface"""
        sources = load_media_sources()
        # The radio part is the edited station list, not the YAML seed
        if station_store:
            sources["music_streams"] = station_store.as_media_sources()
        return sources

    @router.get("/resolution")
    async def get_resolution():
        """Get current display resolution"""
        if display_detector:
            w, h = display_detector.width, display_detector.height
            rate = display_detector.refresh_rate
        else:
            w, h, rate = 1920, 1080, 60

        return {
            "width": w,
            "height": h,
            "refresh_rate": rate,
            "resolution_string": f"{w}x{h}@{rate}Hz",
        }

    @router.get("/dd.xml")
    async def get_device_description():
        """DIAL device description XML for Chromecast discovery"""
        xml_content = f"""<?xml version="1.0"?>
<root xmlns="urn:schemas-upnp-org:device-1-0">
  <specVersion>
    <major>1</major>
    <minor>0</minor>
  </specVersion>
  <device>
    <deviceType>urn:dial-multiscreen-org:device:dial:1</deviceType>
    <friendlyName>{DEVICE_NAME}</friendlyName>
    <manufacturer>Hackerspace Gent</manufacturer>
    <modelName>HSG Canvas</modelName>
    <UDN>uuid:hsg-canvas-receiver</UDN>
  </device>
</root>"""
        return Response(content=xml_content, media_type="application/xml")

    return router
