"""
System Routes

Handles system status, diagnostics, health checks, and configuration endpoints.
"""
import os
import logging
from datetime import datetime
from typing import TYPE_CHECKING, Optional

import yaml
from fastapi import APIRouter, HTTPException

if TYPE_CHECKING:
    from core.mpv_pools import AudioMPVPool, VideoMPVPool

router = APIRouter()


def load_media_sources():
    """Load media sources from YAML configuration file"""
    try:
        config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'media_sources.yaml')
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        else:
            logging.warning(f"Media sources config not found at {config_path}")
            return {"music_streams": {}, "youtube_channels": {}}
    except Exception as e:
        logging.error(f"Error loading media sources: {e}")
        return {"music_streams": {}, "youtube_channels": {}}


def setup_system_routes(
    audio_pool: Optional['AudioMPVPool'] = None,
    video_pool: Optional['VideoMPVPool'] = None,
    display_detector=None
) -> APIRouter:
    """
    Setup system routes with dependency injection

    Args:
        audio_pool: Optional AudioMPVPool for pool status
        video_pool: Optional VideoMPVPool for pool status
        display_detector: Optional DisplayDetector for resolution info

    Returns:
        Configured APIRouter
    """

    @router.get("/health")
    async def health_check():
        """Health check endpoint"""
        return {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "version": "3.0.0-refactored",
            "architecture": "modular"
        }

    @router.get("/status")
    async def get_status():
        """
        Get overall system and streaming status

        Note: This endpoint aggregates data from multiple managers.
        Full implementation requires access to all managers in main.py.
        """
        # This will be fully implemented in main.py where all managers are available
        status = {
            "timestamp": datetime.now().isoformat(),
            "audio_pool": {},
            "video_pool": {},
            "message": "Status endpoint requires unified manager integration"
        }

        if audio_pool:
            status["audio_pool"] = {
                "pool_size": audio_pool.pool_size,
                "total_processes": len(audio_pool.processes),
                "active": sum(1 for s in audio_pool.process_status.values() if s.get("status") == "busy")
            }

        if video_pool:
            status["video_pool"] = {
                "pool_size": video_pool.pool_size,
                "total_processes": len(video_pool.processes),
                "active": sum(1 for s in video_pool.process_status.values() if s.get("status") == "busy")
            }

        return status

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
        return load_media_sources()

    @router.get("/resolution")
    async def get_resolution():
        """Get current display resolution"""
        if display_detector:
            return {
                "width": display_detector.width,
                "height": display_detector.height,
                "refresh_rate": display_detector.refresh_rate,
                "optimal_connector": display_detector.optimal_connector
            }
        else:
            return {
                "width": 1920,
                "height": 1080,
                "refresh_rate": 60,
                "message": "Display detector not available"
            }

    @router.get("/debug/mpv-pool-status")
    async def debug_mpv_pool_status():
        """Debug endpoint to check MPV pool status"""
        try:
            status = {
                "audio_pool": {},
                "video_pool": {}
            }

            if audio_pool:
                status["audio_pool"] = {
                    "initialized": len(audio_pool.processes) > 0,
                    "pool_size": audio_pool.pool_size,
                    "total_processes": len(audio_pool.processes),
                    "processes": {}
                }

                for process_id, proc_status in audio_pool.process_status.items():
                    process = audio_pool.processes.get(process_id)
                    controller = audio_pool.controllers.get(process_id)

                    status["audio_pool"]["processes"][process_id] = {
                        "status": proc_status.get("status"),
                        "content_type": proc_status.get("content_type"),
                        "process_alive": process.poll() is None if process else False,
                        "controller_connected": controller.connected if controller else False,
                        "controller_in_use": controller.in_use if controller else False
                    }

            if video_pool:
                status["video_pool"] = {
                    "initialized": len(video_pool.processes) > 0,
                    "pool_size": video_pool.pool_size,
                    "total_processes": len(video_pool.processes),
                    "processes": {}
                }

                for process_id, proc_status in video_pool.process_status.items():
                    process = video_pool.processes.get(process_id)
                    controller = video_pool.controllers.get(process_id)

                    status["video_pool"]["processes"][process_id] = {
                        "status": proc_status.get("status"),
                        "content_type": proc_status.get("content_type"),
                        "process_alive": process.poll() is None if process else False,
                        "controller_connected": controller.connected if controller else False,
                        "controller_in_use": controller.in_use if controller else False
                    }

            return status
        except Exception as e:
            logging.error(f"Failed to get MPV pool status: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to get pool status: {str(e)}")

    @router.post("/debug/init-mpv-pool")
    async def debug_init_mpv_pool():
        """Debug endpoint to manually initialize MPV pools"""
        try:
            results = {}

            if audio_pool:
                await audio_pool.initialize()
                results["audio_pool"] = "initialized"

            if video_pool:
                await video_pool.initialize()
                results["video_pool"] = "initialized"

            return {"success": True, **results}
        except Exception as e:
            logging.error(f"Failed to initialize MPV pools: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to initialize: {str(e)}")

    @router.get("/docs/quick-start")
    async def quick_start_docs():
        """API quick start documentation"""
        return {
            "message": "HSG Canvas API Quick Start",
            "version": "3.0.0-refactored",
            "architecture": "Modular design with specialized managers",
            "endpoints": {
                "audio": "/audio/* - Audio streaming endpoints",
                "playback": "/playback/* - Video playback endpoints",
                "streams": "/streams/* - Stream republishing endpoints",
                "display": "/display/* - Image and QR display",
                "background": "/background/* - Background mode control",
                "cec": "/cec/* - HDMI-CEC TV control",
                "system": "/status, /health, /diagnostics - System info"
            },
            "recommended_workflow": [
                "1. Check /health to verify system is running",
                "2. Use /audio/start to play audio streams",
                "3. Use /playback/youtube to play YouTube videos",
                "4. Use /background/show to display background"
            ]
        }

    @router.get("/test/drm")
    async def test_drm():
        """Test DRM/KMS capabilities (placeholder)"""
        return {
            "message": "DRM test requires display_detector",
            "status": "pending_integration"
        }

    return router
