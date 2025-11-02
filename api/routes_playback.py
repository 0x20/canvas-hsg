"""
Playback Routes

Handles all video playback endpoints including YouTube and stream playback.
"""
import logging
from typing import TYPE_CHECKING

from fastapi import APIRouter, HTTPException

from models.request_models import YoutubePlayRequest, PlaybackStartRequest

if TYPE_CHECKING:
    from managers.playback_manager import PlaybackManager

router = APIRouter()


def setup_playback_routes(playback_manager: 'PlaybackManager') -> APIRouter:
    """
    Setup playback routes with dependency injection

    Args:
        playback_manager: PlaybackManager instance for video playback

    Returns:
        Configured APIRouter
    """

    @router.post("/playback/youtube")
    async def play_youtube_video(request: YoutubePlayRequest):
        """Play a YouTube video with DRM acceleration"""
        try:
            success = await playback_manager.play_youtube(request.youtube_url, request.duration, request.mute)
            if success:
                duration_text = f" for {request.duration}s" if request.duration else ""
                mute_text = " (muted)" if request.mute else ""
                return {"message": f"Playing YouTube video with DRM acceleration{duration_text}{mute_text}"}
            else:
                raise HTTPException(status_code=500, detail="Failed to play YouTube video")
        except Exception as e:
            # Extract meaningful error details from mpv/youtube-dl failures
            error_msg = str(e)
            if "Requested format is not available" in error_msg:
                detail = "This video format is not supported. Try a different video or check if the video is available in your region."
            elif "youtube" in error_msg.lower() and "error" in error_msg.lower():
                detail = f"YouTube error: {error_msg}"
            elif "No video ID" in error_msg:
                detail = "Invalid YouTube URL. Please check the video URL and try again."
            elif "Private video" in error_msg or "unavailable" in error_msg.lower():
                detail = "This video is private or unavailable. Please try a different video."
            else:
                detail = f"Playback failed: {error_msg}"

            raise HTTPException(status_code=400, detail=detail)

    @router.post("/playback/{stream_key}/start")
    async def start_playback(stream_key: str, player: str = "mpv", mode: str = "optimized", protocol: str = "rtmp"):
        """
        Start playback of a stream (placeholder - will use unified manager in main.py)

        Note: This endpoint is kept for API compatibility but actual implementation
        will depend on the unified visual content manager in main.py
        """
        # This will be handled by a higher-level manager that coordinates
        # playback_manager, background_manager, etc.
        raise HTTPException(status_code=501, detail="Stream playback will be implemented in main.py with unified manager")

    @router.delete("/playback/stop")
    async def stop_playback():
        """Stop current playback"""
        success = await playback_manager.stop_playback()
        if success:
            return {"message": "Playback stopped"}
        else:
            raise HTTPException(status_code=500, detail="Failed to stop playback")

    @router.post("/playback/youtube/volume")
    async def set_youtube_volume(request: dict):
        """Set volume for YouTube playback"""
        volume = request.get('volume', 80)
        if not playback_manager.video_controller:
            raise HTTPException(status_code=404, detail="No active YouTube playback")

        controller = playback_manager.video_controller
        if not controller.connected:
            raise HTTPException(status_code=500, detail="Playback controller not available")

        # Clamp volume to valid range
        volume = max(0, min(130, volume))

        result = await controller.set_property("volume", volume)
        if result.get('error') == 'success':
            return {"message": f"YouTube volume set to {volume}%", "volume": volume}
        else:
            raise HTTPException(status_code=500, detail=f"Failed to set volume: {result}")

    @router.post("/playback/{stream_key}/volume")
    async def set_volume(stream_key: str, volume: int):
        """Set volume for current playback"""
        if stream_key != playback_manager.current_stream:
            raise HTTPException(status_code=404, detail="Stream not currently playing")

        if not playback_manager.video_controller:
            raise HTTPException(status_code=404, detail="No active playback")

        controller = playback_manager.video_controller
        if not controller.connected:
            raise HTTPException(status_code=500, detail="Playback controller not available")

        # Clamp volume to valid range
        volume = max(0, min(130, volume))

        result = await controller.set_property("volume", volume)
        if result.get('error') == 'success':
            return {"message": f"Volume set to {volume}%", "volume": volume}
        else:
            raise HTTPException(status_code=500, detail=f"Failed to set volume: {result}")

    @router.post("/playback/{stream_key}/volume/adjust")
    async def adjust_volume(stream_key: str, adjustment: int):
        """Adjust volume by relative amount"""
        if stream_key != playback_manager.current_stream:
            raise HTTPException(status_code=404, detail="Stream not currently playing")

        if not playback_manager.video_controller:
            raise HTTPException(status_code=404, detail="No active playback")

        controller = playback_manager.video_controller
        if not controller.connected:
            raise HTTPException(status_code=500, detail="Playback controller not available")

        result = await controller.add_property("volume", adjustment)
        if result.get('error') == 'success':
            # Get current volume for response
            vol_result = await controller.get_property("volume")
            current_volume = vol_result.get('data', 'unknown')
            return {"message": f"Volume adjusted by {adjustment}", "current_volume": current_volume}
        else:
            raise HTTPException(status_code=500, detail=f"Failed to adjust volume: {result}")

    @router.post("/playback/{stream_key}/pause")
    async def toggle_pause(stream_key: str, pause: bool = None):
        """Toggle pause/play or set specific pause state"""
        if stream_key != playback_manager.current_stream:
            raise HTTPException(status_code=404, detail="Stream not currently playing")

        if not playback_manager.video_controller:
            raise HTTPException(status_code=404, detail="No active playback")

        controller = playback_manager.video_controller
        if not controller.connected:
            raise HTTPException(status_code=500, detail="Playback controller not available")

        result = await controller.pause(pause)
        if result.get('error') == 'success':
            action = "paused" if pause else ("unpaused" if pause is False else "toggled")
            return {"message": f"Playback {action}"}
        else:
            raise HTTPException(status_code=500, detail=f"Failed to pause/unpause: {result}")

    @router.post("/playback/{stream_key}/seek")
    async def seek_playback(stream_key: str, position: float, mode: str = "absolute"):
        """Seek to position in playback"""
        if stream_key != playback_manager.current_stream:
            raise HTTPException(status_code=404, detail="Stream not currently playing")

        if not playback_manager.video_controller:
            raise HTTPException(status_code=404, detail="No active playback")

        controller = playback_manager.video_controller
        if not controller.connected:
            raise HTTPException(status_code=500, detail="Playback controller not available")

        result = await controller.seek(position, mode)
        if result.get('error') == 'success':
            return {"message": f"Seeked to {position} ({mode})", "position": position, "mode": mode}
        else:
            raise HTTPException(status_code=500, detail=f"Failed to seek: {result}")

    @router.get("/playback/{stream_key}/status")
    async def get_playback_status(stream_key: str):
        """Get detailed playback status via IPC"""
        if stream_key != playback_manager.current_stream:
            raise HTTPException(status_code=404, detail="Stream not currently playing")

        if not playback_manager.video_controller:
            raise HTTPException(status_code=404, detail="No active playback")

        controller = playback_manager.video_controller

        # Gather stats from mpv via IPC
        stats = {}
        try:
            # Get various playback properties
            properties = ["duration", "time-pos", "volume", "pause", "speed", "filename"]
            for prop in properties:
                result = await controller.get_property(prop)
                if result.get('error') == 'success':
                    stats[prop.replace('-', '_')] = result.get('data')
        except Exception as e:
            logging.warning(f"Error getting playback stats: {e}")

        return {
            "stream_key": stream_key,
            "process_id": controller.process_id,
            "protocol": playback_manager.current_protocol,
            "player": playback_manager.current_player,
            **stats
        }

    @router.post("/playback/{stream_key}/speed")
    async def set_playback_speed(stream_key: str, speed: float):
        """Set playback speed multiplier"""
        if stream_key != playback_manager.current_stream:
            raise HTTPException(status_code=404, detail="Stream not currently playing")

        if not playback_manager.video_controller:
            raise HTTPException(status_code=404, detail="No active playback")

        controller = playback_manager.video_controller
        if not controller.connected:
            raise HTTPException(status_code=500, detail="Playback controller not available")

        # Clamp speed to reasonable range
        speed = max(0.1, min(4.0, speed))

        result = await controller.set_property("speed", speed)
        if result.get('error') == 'success':
            return {"message": f"Playback speed set to {speed}x", "speed": speed}
        else:
            raise HTTPException(status_code=500, detail=f"Failed to set speed: {result}")

    @router.post("/playback/switch/{stream_key}")
    async def switch_stream(stream_key: str):
        """
        Quickly switch to different stream (placeholder)

        Note: Stream switching requires unified manager - will be implemented in main.py
        """
        raise HTTPException(status_code=501, detail="Stream switching will be implemented in main.py with unified manager")

    @router.post("/playback/player/{player}")
    async def switch_player(player: str, mode: str = "optimized"):
        """
        Switch to different player (placeholder)

        Note: Player switching requires unified manager - will be implemented in main.py
        """
        raise HTTPException(status_code=501, detail="Player switching will be implemented in main.py with unified manager")

    return router
