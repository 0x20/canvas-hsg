"""Chromecast casting and unified output target routes."""
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException

from models.request_models import (
    AudioStreamRequest,
    ChromecastStartRequest,
    ChromecastVolumeRequest,
    YoutubePlayRequest,
)
from utils.route_helpers import manager_operation


def setup_chromecast_routes(chromecast_manager) -> APIRouter:
    router = APIRouter()

    @router.get("/chromecast/discover")
    async def discover_chromecasts():
        """Discover Chromecast devices on the network"""
        try:
            devices = await chromecast_manager.discover_devices()
            return {
                "devices": devices,
                "count": len(devices)
            }
        except Exception as e:
            logging.error(f"Failed to discover Chromecast devices: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/chromecast/start")
    async def start_chromecast(request: ChromecastStartRequest):
        """Start casting media to a Chromecast device"""
        try:
            success = await chromecast_manager.start_cast(
                media_url=request.media_url,
                device_name=request.device_name,
                content_type=request.content_type,
                title=request.title
            )
            if success:
                return {
                    "message": f"Started casting to {chromecast_manager.current_cast.name}",
                    "media_type": chromecast_manager.current_media_type
                }
            else:
                raise HTTPException(status_code=500, detail="Failed to start casting")
        except HTTPException:
            raise
        except Exception as e:
            logging.error(f"Failed to start casting: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/chromecast/stop")
    async def stop_chromecast():
        """Stop the current cast"""
        return await manager_operation(
            chromecast_manager.stop_cast(),
            {"message": "Cast stopped"},
            "Failed to stop cast",
            "stop cast",
        )

    @router.post("/chromecast/pause")
    async def pause_chromecast():
        """Pause the current cast"""
        if not chromecast_manager.media_controller:
            raise HTTPException(status_code=409, detail="No active cast to pause")
        return await manager_operation(
            chromecast_manager.pause_cast(),
            {"message": "Cast paused"},
            "Failed to pause cast",
            "pause cast",
        )

    @router.post("/chromecast/play")
    async def play_chromecast():
        """Resume/play the current cast"""
        if not chromecast_manager.media_controller:
            raise HTTPException(status_code=409, detail="No active cast to play")
        return await manager_operation(
            chromecast_manager.play_cast(),
            {"message": "Cast resumed"},
            "Failed to play cast",
            "play cast",
        )

    @router.put("/chromecast/volume")
    async def set_chromecast_volume(request: ChromecastVolumeRequest):
        """Set Chromecast volume (0.0-1.0)"""
        try:
            success = await chromecast_manager.set_volume(request.volume)
            if success:
                return {"message": f"Chromecast volume set to {request.volume}"}
            else:
                raise HTTPException(status_code=404, detail="No active Chromecast")
        except HTTPException:
            raise
        except Exception as e:
            logging.error(f"Failed to set Chromecast volume: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/chromecast/status")
    async def get_chromecast_status():
        """Get current casting status"""
        try:
            return chromecast_manager.get_cast_status()
        except Exception as e:
            logging.error(f"Failed to get cast status: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    return router


def setup_output_target_routes(output_target_manager) -> APIRouter:
    router = APIRouter()

    @router.get("/targets")
    async def get_all_targets():
        """Get list of all available output targets (HDMI, Audio Hat, Chromecasts)"""
        try:
            return {
                "targets": output_target_manager.get_all_targets(),
                "defaults": {
                    "video": output_target_manager.default_video_target,
                    "audio": output_target_manager.default_audio_target
                },
                "active": {
                    "video": output_target_manager.active_video_target,
                    "audio": output_target_manager.active_audio_target
                }
            }
        except Exception as e:
            logging.error(f"Failed to get targets: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/targets/refresh")
    async def refresh_targets():
        """Refresh Chromecast discovery"""
        try:
            count = await output_target_manager.discover_chromecast_targets()
            return {
                "message": f"Discovered {count} Chromecast device(s)",
                "chromecasts_found": count,
                "total_targets": len(output_target_manager.targets)
            }
        except Exception as e:
            logging.error(f"Failed to refresh targets: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/targets/status")
    async def get_target_status():
        """Get current output target status"""
        try:
            return output_target_manager.get_status()
        except Exception as e:
            logging.error(f"Failed to get target status: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/targets/{target_id}")
    async def get_target_info(target_id: str):
        """Get information about a specific target"""
        try:
            target = output_target_manager.get_target(target_id)
            if not target:
                raise HTTPException(status_code=404, detail=f"Target {target_id} not found")
            return target.to_dict()
        except HTTPException:
            raise
        except Exception as e:
            logging.error(f"Failed to get target info: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/targets/play/video")
    async def play_video_on_target(request: YoutubePlayRequest, target: Optional[str] = None):
        """
        Play video on specified target (or default)

        Query params:
            target: Target ID (e.g., 'local-video', 'chromecast-12345')
        """
        try:
            success = await output_target_manager.play_video(
                video_url=request.youtube_url,
                target_id=target,
                duration=request.duration,
                mute=request.mute
            )
            if success:
                target_name = target or output_target_manager.default_video_target
                return {
                    "message": f"Video playback started on {target_name}",
                    "target": target_name,
                    "url": request.youtube_url
                }
            else:
                raise HTTPException(status_code=500, detail="Failed to start video playback")
        except HTTPException:
            raise
        except Exception as e:
            logging.error(f"Failed to play video: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/targets/play/audio")
    async def play_audio_on_target(request: AudioStreamRequest, target: Optional[str] = None):
        """
        Play audio on specified target (or default)

        Query params:
            target: Target ID (e.g., 'local-audio', 'chromecast-12345')
        """
        try:
            success = await output_target_manager.play_audio(
                audio_url=request.stream_url,
                target_id=target,
                volume=request.volume
            )
            if success:
                target_name = target or output_target_manager.default_audio_target
                return {
                    "message": f"Audio playback started on {target_name}",
                    "target": target_name,
                    "url": request.stream_url
                }
            else:
                raise HTTPException(status_code=500, detail="Failed to start audio playback")
        except HTTPException:
            raise
        except Exception as e:
            logging.error(f"Failed to play audio: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/targets/stop")
    async def stop_playback_on_targets(media_type: str = "all"):
        """
        Stop playback on active targets

        Query params:
            media_type: 'video', 'audio', or 'all' (default: 'all')
        """
        try:
            await output_target_manager.stop_playback(media_type)
            return {
                "message": f"Stopped {media_type} playback",
                "media_type": media_type
            }
        except Exception as e:
            logging.error(f"Failed to stop playback: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    return router
