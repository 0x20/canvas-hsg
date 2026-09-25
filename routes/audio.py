"""Audio stream, station art and Spotify Connect routes."""
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException

from config import DEVICE_NAME
from managers import system_audio
from models.request_models import (
    AudioStreamRequest,
    AudioVolumeRequest,
    SpotifyEventRequest,
    SpotifyVolumeRequest,
)


def setup_audio_routes(audio_manager, spotify_manager=None) -> APIRouter:
    router = APIRouter()

    @router.post("/audio/start")
    async def start_audio_stream(request: AudioStreamRequest):
        """Start audio streaming (supports soma.fm and other audio streams)"""
        success = await audio_manager.start_audio_stream(request.stream_url, request.volume)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to start audio stream")
        volume_text = f" at volume {request.volume}" if request.volume is not None else ""
        return {"message": f"Audio stream started: {request.stream_url}{volume_text}"}

    @router.get("/audio/station-art")
    async def station_art_status():
        """What the station-logo cache currently holds."""
        if not audio_manager.station_art:
            raise HTTPException(status_code=503, detail="Station art cache not available")
        return audio_manager.station_art.status()

    @router.post("/audio/station-art/refresh")
    async def station_art_refresh(stream_url: Optional[str] = None):
        """Drop cached art so it is re-resolved on the next play.

        Without `stream_url` this clears the whole cache — useful after editing
        an `image:` in media_sources.yaml, or to retry stations that had no art
        when they were first looked up.
        """
        if not audio_manager.station_art:
            raise HTTPException(status_code=503, detail="Station art cache not available")
        removed = audio_manager.station_art.clear(stream_url)
        return {"message": f"Cleared {removed} station art entrie(s)", "cleared": removed}

    @router.post("/audio/stop")
    async def stop_audio_stream():
        """Stop current audio stream"""
        if not await audio_manager.stop_audio_stream():
            raise HTTPException(status_code=500, detail="Failed to stop audio stream")
        return {"message": "Audio stream stopped"}

    @router.get("/audio/status")
    async def get_audio_status():
        """Get current audio streaming status across all sources.

        Returns:
            - **is_playing** (bool): True if any audio source is active
            - **sources** (list[str]): Active sources, any combination of:
              `"audio_stream"`, `"spotify"`, `"sendspin"`, `"bluetooth"`, `"youtube"`
            - **volume** (int): Current volume (0-100)
            - **current_stream** (str): Stream URL (only when `audio_stream` is active)
            - **stream_name** (str): Friendly name (only when `audio_stream` is active)
            - **metadata** (object): Stream metadata (only when `audio_stream` is active and metadata available)
        """
        return audio_manager.get_audio_status()

    @router.post("/audio/pause")
    async def toggle_audio_pause():
        """Toggle audio pause/play via WebSocket"""
        if not audio_manager.current_audio_stream:
            raise HTTPException(status_code=404, detail="No active audio stream")
        if not await audio_manager.toggle_pause():
            raise HTTPException(status_code=500, detail="Failed to toggle audio pause")
        return {"message": "Audio pause toggled"}

    @router.put("/audio/volume")
    async def set_audio_volume(request: AudioVolumeRequest):
        """Set the browser audio volume (0-100)"""
        if not await audio_manager.set_volume(request.volume):
            raise HTTPException(status_code=500, detail="Failed to set audio volume")
        return {"message": f"Audio volume set to {request.volume}"}

    @router.get("/audio/spotify/status")
    async def get_spotify_status():
        """Get Spotify Connect (Raspotify) service status"""
        is_running = await system_audio.service_active("raspotify")
        volume = await system_audio.get_spotify_volume()
        return {
            "service_running": is_running,
            "device_name": DEVICE_NAME,
            "status": "active" if is_running else "inactive",
            "volume": volume if volume is not None else 100,
            "message": "Spotify Connect is available - cast from your phone!" if is_running else "Spotify Connect service is not running",
        }

    @router.put("/audio/spotify/volume")
    async def set_spotify_volume(request: SpotifyVolumeRequest):
        """Set Spotify Connect (Raspotify) volume using ALSA mixer"""
        if not await system_audio.set_spotify_volume(request.volume):
            raise HTTPException(status_code=500, detail="Failed to set Spotify volume")
        return {
            "success": True,
            "volume": request.volume,
            "message": f"Spotify volume set to {request.volume}%",
        }

    @router.post("/audio/spotify/event")
    async def handle_spotify_event(request: SpotifyEventRequest):
        """Handle Spotify Connect (Raspotify) events from librespot onevent hook"""
        logging.info(f"Spotify event received: {request.event}")
        if not spotify_manager:
            logging.warning("No SpotifyManager available to handle event")
        elif not await spotify_manager.handle_event(
            event=request.event,
            track_id=request.track_id,
            old_track_id=request.old_track_id,
            duration_ms=request.duration_ms,
            position_ms=request.position_ms,
            name=request.name,
            artists=request.artists,
            album=request.album,
            covers=request.covers,
        ):
            logging.warning(f"SpotifyManager failed to handle event: {request.event}")
        return {
            "success": True,
            "event": request.event,
            "message": f"Event '{request.event}' processed successfully",
        }

    @router.get("/audio/spotify/playback")
    async def get_spotify_playback():
        """Get current Spotify playback information"""
        if not spotify_manager:
            return {
                "is_playing": False,
                "is_session_connected": False,
                "message": "SpotifyManager not available",
            }
        return spotify_manager.get_status()

    return router
