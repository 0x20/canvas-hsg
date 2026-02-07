"""
Unified Routes Module

Consolidates all API route definitions from the api/ directory into a single file.
Provides setup functions for each route group that can be imported by main.py.
"""
import logging
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Optional

import yaml
from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import Response
from utils.route_helpers import require_video_controller, manager_operation

from models.request_models import (
    AudioStreamRequest,
    AudioVolumeRequest,
    YoutubePlayRequest,
    PlaybackStartRequest,
    QRCodeRequest,
    ImageDisplayRequest,
    ChromecastStartRequest,
    ChromecastVolumeRequest,
    CastReceiveRequest,
    SpotifyEventRequest,
    PlaybackVolumeRequest,
    BackgroundModeRequest,
    SpotifyVolumeRequest,
    WebcastStartRequest,
    WebcastConfigRequest,
    WebcastScrollRequest,
    WebcastJumpRequest,
)

if TYPE_CHECKING:
    from managers.audio_manager import AudioManager
    from managers.playback_manager import PlaybackManager
    from managers.stream_manager import StreamManager
    from managers.screen_stream_manager import ScreenStreamManager
    from managers.image_manager import ImageManager
    from managers.chromecast_manager import ChromecastManager
    from managers.cast_receiver_manager import CastReceiverManager
    from managers.spotify_manager import SpotifyManager
    from managers.background_modes import BackgroundManager
    from managers.webcast_manager import WebcastManager, WebcastConfig
    from managers.mpv_pools import AudioMPVPool, VideoMPVPool


# =============================================================================
# AUDIO ROUTES
# =============================================================================

def setup_audio_routes(audio_manager: 'AudioManager', spotify_manager: Optional['SpotifyManager'] = None) -> APIRouter:
    """
    Setup audio routes with dependency injection

    Args:
        audio_manager: AudioManager instance for audio streaming
        spotify_manager: Optional SpotifyManager instance for Spotify integration

    Returns:
        Configured APIRouter
    """
    router = APIRouter()

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

            from config import DEVICE_NAME
            return {
                "service_running": is_running,
                "device_name": DEVICE_NAME,
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
    async def set_spotify_volume(request: SpotifyVolumeRequest):
        """Set Spotify Connect (Raspotify) volume using ALSA mixer"""
        try:
            volume = request.volume

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

    @router.post("/audio/spotify/event")
    async def handle_spotify_event(request: SpotifyEventRequest):
        """Handle Spotify Connect (Raspotify) events from librespot onevent hook"""
        try:
            logging.info(f"Spotify event received: {request.event}")
            logging.debug(f"Event details - Track: {request.track_id}, Duration: {request.duration_ms}ms, Position: {request.position_ms}ms")

            # Forward event to SpotifyManager if available
            if spotify_manager:
                success = await spotify_manager.handle_event(
                    event=request.event,
                    track_id=request.track_id,
                    old_track_id=request.old_track_id,
                    duration_ms=request.duration_ms,
                    position_ms=request.position_ms,
                    name=request.name,
                    artists=request.artists,
                    album=request.album,
                    covers=request.covers,
                )

                if not success:
                    logging.warning(f"SpotifyManager failed to handle event: {request.event}")
            else:
                logging.warning("No SpotifyManager available to handle event")

            return {
                "success": True,
                "event": request.event,
                "message": f"Event '{request.event}' processed successfully"
            }

        except Exception as e:
            logging.error(f"Error handling Spotify event: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/audio/spotify/playback")
    async def get_spotify_playback():
        """Get current Spotify playback information"""
        try:
            if spotify_manager:
                return spotify_manager.get_status()
            else:
                return {
                    "is_playing": False,
                    "is_session_connected": False,
                    "message": "SpotifyManager not available"
                }
        except Exception as e:
            logging.error(f"Error getting Spotify playback status: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    return router


# =============================================================================
# PLAYBACK ROUTES
# =============================================================================

def setup_playback_routes(playback_manager: 'PlaybackManager') -> APIRouter:
    """
    Setup playback routes with dependency injection

    Args:
        playback_manager: PlaybackManager instance for video playback

    Returns:
        Configured APIRouter
    """
    router = APIRouter()

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
            elif "private" in error_msg.lower() or "authentication" in error_msg.lower() or "unavailable" in error_msg.lower():
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
    async def set_youtube_volume(request: PlaybackVolumeRequest):
        """Set volume for YouTube playback"""
        controller = require_video_controller(playback_manager)
        volume = request.volume

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

        controller = require_video_controller(playback_manager)

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

        controller = require_video_controller(playback_manager)

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

        controller = require_video_controller(playback_manager)

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

        controller = require_video_controller(playback_manager)

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

        controller = require_video_controller(playback_manager)

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

        controller = require_video_controller(playback_manager)

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


# =============================================================================
# STREAM ROUTES
# =============================================================================

def setup_stream_routes(stream_manager: 'StreamManager') -> APIRouter:
    """
    Setup stream routes with dependency injection

    Args:
        stream_manager: StreamManager instance for stream republishing

    Returns:
        Configured APIRouter
    """
    router = APIRouter()

    @router.post("/streams/{stream_key}/start")
    async def start_stream(stream_key: str, source_url: str, protocol: str = "rtmp"):
        """Start publishing a GPU-accelerated stream using specified protocol"""
        success = await stream_manager.start_stream(stream_key, source_url, protocol)
        if success:
            return {"message": f"GPU-accelerated stream {stream_key} started via {protocol.upper()}"}
        else:
            raise HTTPException(status_code=500, detail=f"Failed to start {protocol} stream")

    @router.delete("/streams/{stream_key}")
    async def stop_stream(stream_key: str):
        """Stop a specific stream"""
        success = await stream_manager.stop_stream(stream_key)
        if success:
            return {"message": f"Stream {stream_key} stopped"}
        else:
            raise HTTPException(status_code=404, detail="Stream not found")

    @router.get("/streams")
    async def list_streams():
        """List all active streams"""
        streams = {}
        for key, info in stream_manager.active_streams.items():
            streams[key] = {
                "source_url": info["source_url"],
                "protocol": info["protocol"],
                "started_at": info["started_at"],
                "status": info["status"]
            }

        return {
            "active_streams": streams,
            "stream_count": len(streams)
        }

    return router


# =============================================================================
# SCREEN ROUTES
# =============================================================================

def setup_screen_routes(screen_stream_manager: 'ScreenStreamManager') -> APIRouter:
    """
    Setup screen streaming routes with dependency injection

    Args:
        screen_stream_manager: ScreenStreamManager instance for screen capture

    Returns:
        Configured APIRouter
    """
    router = APIRouter()

    @router.post("/screen-stream/{stream_key}/start")
    async def start_screen_stream(stream_key: str, protocol: str = "rtmp"):
        """Start streaming the display output"""
        success = await screen_stream_manager.start_screen_stream(stream_key, protocol)
        if success:
            return {"message": f"Screen streaming started: {stream_key} via {protocol.upper()}"}
        else:
            raise HTTPException(status_code=500, detail=f"Failed to start screen streaming via {protocol}")

    @router.delete("/screen-stream/stop")
    async def stop_screen_stream():
        """Stop screen streaming"""
        success = await screen_stream_manager.stop_screen_stream()
        if success:
            return {"message": "Screen streaming stopped"}
        else:
            raise HTTPException(status_code=404, detail="No active screen stream")

    @router.get("/screen-stream/status")
    async def get_screen_stream_status():
        """Get screen streaming status"""
        return screen_stream_manager.get_screen_stream_info()

    @router.get("/screen-stream/capabilities")
    async def get_screen_capture_capabilities():
        """
        Check FFmpeg and DRM capabilities for screen capture

        Note: This is a placeholder - actual implementation depends on
        access to display_detector and other system components
        """
        # This will be implemented when we have access to display_detector
        # and can check FFmpeg capabilities
        return {
            "message": "Capability detection will be implemented in main.py",
            "methods_supported": ["framebuffer", "kmsgrab"]
        }

    return router


# =============================================================================
# DISPLAY ROUTES
# =============================================================================

def setup_display_routes(image_manager: 'ImageManager', background_manager=None) -> APIRouter:
    """
    Setup display routes with dependency injection

    Args:
        image_manager: ImageManager instance for image/QR display
        background_manager: BackgroundManager for auto-return to background

    Returns:
        Configured APIRouter
    """
    router = APIRouter()

    @router.post("/display/qrcode")
    async def display_qr_code(request: QRCodeRequest):
        """Generate and display a QR code with text overlay"""
        success = await image_manager.display_qr_code(request.content, request.duration, background_manager)
        if success:
            duration_text = f" for {request.duration}s" if request.duration else " (forever)"
            return {"message": f"Displaying QR code for '{request.content}'{duration_text}"}
        else:
            raise HTTPException(status_code=500, detail="Failed to generate and display QR code")

    @router.post("/display/image")
    async def display_image_endpoint(file: UploadFile = File(...), duration: int = 10):
        """Upload and display an image on screen"""
        try:
            image_data = await file.read()
            temp_dir = Path("/tmp/stream_images")
            temp_dir.mkdir(exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            image_path = temp_dir / f"upload_{timestamp}_{file.filename}"

            with open(image_path, "wb") as f:
                f.write(image_data)

            success = await image_manager.display_image(str(image_path), duration, background_manager)

            if success:
                return {"message": f"Displaying image for {duration} seconds", "path": str(image_path)}
            else:
                raise HTTPException(status_code=500, detail="Failed to display image")

        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to upload image: {str(e)}")

    @router.post("/display/image/base64")
    async def display_image_base64(request: ImageDisplayRequest):
        """Display a base64 encoded image"""
        success = await image_manager.save_and_display_image(request.image_data, request.duration, background_manager)
        if success:
            return {"message": f"Displaying image for {request.duration} seconds"}
        else:
            raise HTTPException(status_code=500, detail="Failed to display image")

    return router


# =============================================================================
# BACKGROUND ROUTES
# =============================================================================

def setup_background_routes(background_manager: 'BackgroundManager') -> APIRouter:
    """
    Setup background routes with dependency injection

    Args:
        background_manager: BackgroundManager instance for background display

    Returns:
        Configured APIRouter
    """
    router = APIRouter()

    @router.post("/background/show")
    async def show_background():
        """Show the background display"""
        try:
            # Note: stop_all_visual_content() will be called by unified manager in main.py
            await background_manager.start_static_mode_with_audio_status(show_audio_icon=False)
            return {"message": "Showing background"}
        except Exception as e:
            logging.error(f"Failed to show background: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to show background: {str(e)}")

    @router.post("/background/set")
    async def set_background(file: UploadFile = File(...)):
        """Set a new static background image"""
        # Note: stop_all_visual_content() will be called by unified manager in main.py
        try:
            from config import DEFAULT_BACKGROUND_PATH

            image_data = await file.read()
            temp_dir = Path("/tmp/stream_images")
            temp_dir.mkdir(exist_ok=True)

            # Save the uploaded image
            with open(DEFAULT_BACKGROUND_PATH, "wb") as f:
                f.write(image_data)

            # Restart background to use new image
            await background_manager.stop()
            await background_manager.start_static_mode_with_audio_status(show_audio_icon=False)

            return {"message": "Background image set and scaled to monitor resolution"}

        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to set background: {str(e)}")

    @router.post("/background/mode")
    async def set_background_mode(request: BackgroundModeRequest):
        """Set background display mode (static only)"""
        logging.info(f"POST /background/mode called with mode: {request.mode}")
        # Note: stop_all_visual_content() will be called by unified manager in main.py
        try:
            mode = request.mode
            logging.info(f"Setting background mode to: {mode}")
            if mode != "static":
                raise HTTPException(status_code=400, detail="Invalid mode. Only 'static' mode is supported")

            # Restart background in static mode
            await background_manager.stop()
            await background_manager.start_static_mode_with_audio_status(show_audio_icon=False)

            logging.info(f"Background mode set to: {mode}")
            return {"status": "success", "mode": mode}

        except Exception as e:
            logging.error(f"Failed to set background mode: {e}")
            import traceback
            logging.error(f"Traceback: {traceback.format_exc()}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/background/mode")
    async def get_background_mode():
        """Get current background mode and status"""
        try:
            # Return background manager status
            mode = "static" if background_manager.is_running else "none"
            return {
                "mode": mode,
                "active": background_manager.is_running
            }
        except Exception as e:
            logging.error(f"Failed to get background status: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/background/refresh")
    async def refresh_background():
        """Refresh static background display"""
        # Note: stop_all_visual_content() will be called by unified manager in main.py
        try:
            # Restart static background mode
            await background_manager.stop()
            await background_manager.start_static_mode_with_audio_status(show_audio_icon=False)
            return {"status": "success", "message": "Static background refreshed"}
        except Exception as e:
            logging.error(f"Failed to refresh background: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    return router


# =============================================================================
# CEC ROUTES
# =============================================================================

def setup_cec_routes(cec_manager) -> APIRouter:
    """
    Setup HDMI-CEC routes with dependency injection

    Args:
        cec_manager: HDMICECManager instance for TV control

    Returns:
        Configured APIRouter
    """
    router = APIRouter()

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


# =============================================================================
# SYSTEM ROUTES
# =============================================================================

def load_media_sources():
    """Load media sources from YAML configuration file"""
    try:
        config_path = os.path.join(os.path.dirname(__file__), 'media_sources.yaml')
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
    router = APIRouter()

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


# =============================================================================
# WEBCAST ROUTES
# =============================================================================

def setup_webcast_routes(webcast_manager: 'WebcastManager') -> APIRouter:
    """
    Setup webcast routes with dependency injection

    Args:
        webcast_manager: WebcastManager instance for website webcasting

    Returns:
        Configured APIRouter
    """
    router = APIRouter()

    @router.post("/webcast/start")
    async def start_webcast(request: WebcastStartRequest):
        """Start webcasting a website with auto-scroll"""
        # Note: stop_all_visual_content() will be called by unified manager in main.py
        try:
            from managers.webcast_manager import WebcastConfig

            # Create webcast configuration from validated request
            config = WebcastConfig(
                url=request.url,
                viewport_width=request.viewport_width,
                viewport_height=request.viewport_height,
                scroll_delay=request.scroll_delay,
                scroll_percentage=request.scroll_percentage,
                overlap_percentage=request.overlap_percentage,
                loop_count=request.loop_count,
                zoom_level=request.zoom_level,
                wait_for_load=request.wait_for_load,
                screenshot_path=request.screenshot_path
            )

            result = await webcast_manager.start_webcast(config)

            return result

        except Exception as e:
            logging.error(f"Failed to start webcast: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/webcast/stop")
    async def stop_webcast():
        """Stop the current webcast"""
        try:
            result = await webcast_manager.stop_webcast()
            return result
        except Exception as e:
            logging.error(f"Failed to stop webcast: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/webcast/status")
    async def get_webcast_status():
        """Get current webcast status"""
        try:
            return await webcast_manager.get_status()
        except Exception as e:
            logging.error(f"Failed to get webcast status: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/webcast/config")
    async def update_webcast_config(request: WebcastConfigRequest):
        """Update webcast configuration"""
        try:
            data = request.model_dump(exclude_none=True)
            result = await webcast_manager.update_config(data)
            return result
        except Exception as e:
            logging.error(f"Failed to update webcast config: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/webcast/scroll")
    async def manual_webcast_scroll(request: WebcastScrollRequest):
        """Manually scroll the webcast"""
        try:
            result = await webcast_manager.manual_scroll(request.direction, request.amount)
            return result
        except Exception as e:
            logging.error(f"Failed to scroll webcast: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/webcast/jump")
    async def jump_webcast_position(request: WebcastJumpRequest):
        """Jump to a specific position in the webcast"""
        try:
            result = await webcast_manager.jump_to_position(request.position_percent)
            return result
        except Exception as e:
            logging.error(f"Failed to jump webcast: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    return router


# =============================================================================
# CHROMECAST ROUTES
# =============================================================================

def setup_chromecast_routes(chromecast_manager: 'ChromecastManager') -> APIRouter:
    """
    Setup Chromecast routes with dependency injection

    Args:
        chromecast_manager: ChromecastManager instance for casting

    Returns:
        Configured APIRouter
    """
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
        return await manager_operation(
            chromecast_manager.pause_cast(),
            {"message": "Cast paused"},
            "No active cast to pause",
            "pause cast",
        )

    @router.post("/chromecast/play")
    async def play_chromecast():
        """Resume/play the current cast"""
        return await manager_operation(
            chromecast_manager.play_cast(),
            {"message": "Cast resumed"},
            "No active cast to play",
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


# =============================================================================
# CAST RECEIVER ROUTES (for receiving casts FROM phones/tablets)
# =============================================================================

def setup_cast_receiver_routes(cast_receiver: 'CastReceiverManager') -> APIRouter:
    """
    Setup Cast Receiver routes with dependency injection

    Args:
        cast_receiver: CastReceiverManager instance for receiving casts

    Returns:
        Configured APIRouter
    """
    router = APIRouter()

    @router.get("/dd.xml")
    async def get_device_description():
        """DIAL device description XML for discovery"""
        try:
            xml_content = cast_receiver.get_device_description_xml()
            return Response(content=xml_content, media_type="application/xml")
        except Exception as e:
            logging.error(f"Failed to get device description: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/cast-receiver/start")
    async def start_receiver():
        """Start the cast receiver (makes Canvas discoverable)"""
        try:
            success = await cast_receiver.start_receiver()
            if success:
                return {
                    "message": "Cast receiver started",
                    "device_name": cast_receiver.device_name,
                    "local_ip": cast_receiver.local_ip
                }
            else:
                raise HTTPException(status_code=500, detail="Failed to start cast receiver")
        except Exception as e:
            logging.error(f"Failed to start cast receiver: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/cast-receiver/stop")
    async def stop_receiver():
        """Stop the cast receiver"""
        return await manager_operation(
            cast_receiver.stop_receiver(),
            {"message": "Cast receiver stopped"},
            "Failed to stop cast receiver",
            "stop cast receiver",
        )

    @router.post("/cast-receiver/receive")
    async def receive_cast(request: CastReceiveRequest):
        """Receive a cast from a phone/tablet"""
        try:
            success = await cast_receiver.receive_cast(
                media_url=request.media_url,
                content_type=request.content_type,
                title=request.title
            )
            if success:
                return {
                    "message": "Cast received and playing",
                    "session_id": cast_receiver.session_id
                }
            else:
                raise HTTPException(status_code=500, detail="Failed to play cast")
        except Exception as e:
            logging.error(f"Failed to receive cast: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/cast-receiver/stop-session")
    async def stop_cast_session():
        """Stop the current cast session"""
        return await manager_operation(
            cast_receiver.stop_session(),
            {"message": "Cast session stopped"},
            "Failed to stop session",
            "stop cast session",
        )

    @router.get("/cast-receiver/status")
    async def get_receiver_status():
        """Get cast receiver status"""
        try:
            return cast_receiver.get_receiver_status()
        except Exception as e:
            logging.error(f"Failed to get receiver status: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    return router


# =============================================================================
# OUTPUT TARGET ROUTES (unified target management)
# =============================================================================

def setup_output_target_routes(output_target_manager: 'OutputTargetManager') -> APIRouter:
    """
    Setup Output Target routes with dependency injection

    Args:
        output_target_manager: OutputTargetManager instance

    Returns:
        Configured APIRouter
    """
    from managers.output_target_manager import OutputTargetManager
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
