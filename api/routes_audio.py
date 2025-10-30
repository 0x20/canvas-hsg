"""
Audio Routes

Handles all audio streaming endpoints including audio streams and Spotify Connect control.
"""
import logging
import re
import subprocess
from typing import TYPE_CHECKING

from fastapi import APIRouter, HTTPException, Request

from models.request_models import AudioStreamRequest, AudioVolumeRequest

if TYPE_CHECKING:
    from managers.audio_manager import AudioManager

router = APIRouter()


def setup_audio_routes(audio_manager: 'AudioManager') -> APIRouter:
    """
    Setup audio routes with dependency injection

    Args:
        audio_manager: AudioManager instance for audio streaming

    Returns:
        Configured APIRouter
    """

    @router.post("/audio/start")
    async def start_audio_stream(request: AudioStreamRequest):
        """Start audio streaming (supports soma.fm and other audio streams)"""
        success = await audio_manager.start_audio_stream(request.stream_url, request.volume)
        if success:
            volume_text = f" at volume {request.volume}" if request.volume is not None else ""
            return {"message": f"Audio stream started: {request.stream_url}{volume_text}"}
        else:
            raise HTTPException(status_code=500, detail="Failed to start audio stream")

    @router.post("/audio/stop")
    async def stop_audio_stream():
        """Stop current audio stream"""
        success = await audio_manager.stop_audio_stream()
        if success:
            return {"message": "Audio stream stopped"}
        else:
            raise HTTPException(status_code=500, detail="Failed to stop audio stream")

    @router.get("/audio/status")
    async def get_audio_status():
        """Get current audio streaming status"""
        return audio_manager.get_audio_status()

    @router.post("/audio/pause")
    async def toggle_audio_pause():
        """Toggle audio pause/play via IPC"""
        if audio_manager.audio_controller:
            result = await audio_manager.audio_controller.send_command(["cycle", "pause"])
            if result.get('error') == 'success':
                return {"message": "Audio pause toggled"}
            else:
                raise HTTPException(status_code=500, detail="Failed to toggle audio pause")
        else:
            raise HTTPException(status_code=404, detail="No active audio stream")

    @router.put("/audio/volume")
    async def set_audio_volume(request: AudioVolumeRequest):
        """Set audio volume via IPC (0-100)"""
        if not 0 <= request.volume <= 100:
            raise HTTPException(status_code=400, detail="Volume must be between 0 and 100")

        success = await audio_manager.set_volume(request.volume)
        if success:
            return {"message": f"Audio volume set to {request.volume}"}
        else:
            raise HTTPException(status_code=500, detail="Failed to set audio volume")

    @router.get("/audio/spotify/status")
    async def get_spotify_status():
        """Get Spotify Connect (Raspotify) service status"""
        try:
            # Check if Raspotify service is running
            result = subprocess.run(
                ["systemctl", "is-active", "raspotify"],
                capture_output=True,
                text=True,
                timeout=5
            )
            is_running = result.stdout.strip() == "active"

            # Get current volume using amixer for CARD 3
            volume = 100  # Default
            try:
                volume_result = subprocess.run(
                    ["amixer", "-c", "3", "get", "PCM"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                # Parse volume from output (e.g., "[75%]")
                match = re.search(r'\[(\d+)%\]', volume_result.stdout)
                if match:
                    volume = int(match.group(1))
            except Exception as vol_error:
                logging.warning(f"Could not get Spotify volume: {vol_error}")

            return {
                "service_running": is_running,
                "device_name": "HSG Canvas",
                "status": "active" if is_running else "inactive",
                "volume": volume,
                "message": "Spotify Connect is available - cast from your phone!" if is_running else "Spotify Connect service is not running"
            }
        except subprocess.TimeoutExpired:
            return {
                "service_running": False,
                "status": "error",
                "message": "Timeout checking Raspotify status"
            }
        except Exception as e:
            logging.error(f"Error checking Spotify status: {e}")
            return {
                "service_running": False,
                "status": "error",
                "message": f"Error: {str(e)}"
            }

    @router.put("/audio/spotify/volume")
    async def set_spotify_volume(request: Request):
        """Set Spotify Connect (Raspotify) volume using ALSA mixer"""
        try:
            data = await request.json()
            volume = data.get("volume", 70)

            if not 0 <= volume <= 100:
                raise HTTPException(status_code=400, detail="Volume must be between 0 and 100")

            # Set volume using amixer for CARD 3
            result = subprocess.run(
                ["amixer", "-c", "3", "set", "PCM", f"{volume}%"],
                capture_output=True,
                text=True,
                timeout=5
            )

            if result.returncode == 0:
                return {
                    "success": True,
                    "volume": volume,
                    "message": f"Spotify volume set to {volume}%"
                }
            else:
                raise HTTPException(status_code=500, detail=f"Failed to set volume: {result.stderr}")

        except subprocess.TimeoutExpired:
            raise HTTPException(status_code=500, detail="Timeout setting volume")
        except Exception as e:
            logging.error(f"Error setting Spotify volume: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    return router
