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
from utils.route_helpers import manager_operation

from models.request_models import (
    AudioStreamRequest,
    AudioVolumeRequest,
    YoutubePlayRequest,
    TwitchPlayRequest,
    QRCodeRequest,
    ImageDisplayRequest,
    ChromecastStartRequest,
    ChromecastVolumeRequest,
    SpotifyEventRequest,
    BackgroundModeRequest,
    StaticOverlayRequest,
    SpotifyVolumeRequest,
    WebcastStartRequest,
    WebcastConfigRequest,
    WebcastScrollRequest,
    WebcastJumpRequest,
    HAConfigUpdateRequest,
    HAAutomationAddRequest,
)

if TYPE_CHECKING:
    from managers.audio_manager import AudioManager
    from managers.playback_manager import PlaybackManager
    from managers.image_manager import ImageManager
    from managers.chromecast_manager import ChromecastManager
    from managers.spotify_manager import SpotifyManager
    from managers.background_modes import BackgroundManager
    from managers.webcast_manager import WebcastManager, WebcastConfig
    from managers.homeassistant_manager import HomeAssistantManager
    from managers.websocket_manager import WebSocketManager
    from managers.display_stack import DisplayStack


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
        """Get current audio streaming status across all sources.

        Returns:
            - **is_playing** (bool): True if any audio source is active
            - **sources** (list[str]): Active sources, any combination of:
              `"audio_stream"`, `"spotify"`, `"sendspin"`, `"youtube"`
            - **volume** (int): Current volume (0-100)
            - **current_stream** (str): Stream URL (only when `audio_stream` is active)
            - **stream_name** (str): Friendly name (only when `audio_stream` is active)
            - **metadata** (object): Stream metadata (only when `audio_stream` is active and metadata available)
        """
        return audio_manager.get_audio_status()

    @router.post("/audio/pause")
    async def toggle_audio_pause():
        """Toggle audio pause/play via WebSocket"""
        if audio_manager.current_audio_stream:
            success = await audio_manager.toggle_pause()
            if success:
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
        """Play a YouTube video via browser (YouTube IFrame API)"""
        try:
            success = await playback_manager.play_youtube(request.youtube_url, request.duration, request.mute)
            if success:
                duration_text = f" for {request.duration}s" if request.duration else ""
                mute_text = " (muted)" if request.mute else ""
                return {"message": f"Playing YouTube video{duration_text}{mute_text}"}
            else:
                raise HTTPException(status_code=500, detail="Failed to play YouTube video")
        except Exception as e:
            error_msg = str(e)
            if "No video ID" in error_msg or "Could not extract" in error_msg:
                detail = "Invalid YouTube URL. Please check the video URL and try again."
            else:
                detail = f"Playback failed: {error_msg}"
            raise HTTPException(status_code=400, detail=detail)

    @router.post("/playback/twitch")
    async def play_twitch_stream(request: TwitchPlayRequest):
        """Play a Twitch channel/VOD/clip via browser (Twitch embedded player)"""
        try:
            success = await playback_manager.play_twitch(request.twitch_url, request.duration, request.mute)
            if success:
                duration_text = f" for {request.duration}s" if request.duration else ""
                mute_text = " (muted)" if request.mute else ""
                return {"message": f"Playing Twitch stream{duration_text}{mute_text}"}
            else:
                raise HTTPException(status_code=400, detail="Invalid Twitch URL. Please check the URL and try again.")
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Playback failed: {e}")

    @router.put("/playback/volume")
    async def set_playback_volume(request: dict):
        """Set system audio volume via PulseAudio (0-100)"""
        volume = request.get("volume")
        if volume is None:
            raise HTTPException(status_code=400, detail="Missing 'volume' field")
        volume = max(0, min(100, int(volume)))

        try:
            result = subprocess.run(
                ["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{volume}%"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                return {"volume": volume}
            else:
                raise HTTPException(status_code=500, detail=f"pactl error: {result.stderr}")
        except subprocess.TimeoutExpired:
            raise HTTPException(status_code=500, detail="Timeout setting volume")

    @router.get("/playback/volume")
    async def get_playback_volume():
        """Get current system audio volume"""
        try:
            result = subprocess.run(
                ["pactl", "get-sink-volume", "@DEFAULT_SINK@"],
                capture_output=True, text=True, timeout=5
            )
            import re
            match = re.search(r'(\d+)%', result.stdout)
            volume = int(match.group(1)) if match else 100
            return {"volume": volume}
        except Exception:
            return {"volume": 100}

    @router.delete("/playback/stop")
    async def stop_playback():
        """Stop current playback"""
        success = await playback_manager.stop_playback()
        if success:
            return {"message": "Playback stopped"}
        else:
            raise HTTPException(status_code=500, detail="Failed to stop playback")

    @router.get("/playback/status")
    async def get_playback_status():
        """Get current playback status"""
        return playback_manager.get_playback_status()

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

    @router.get("/background/overlays")
    async def get_background_overlays():
        """Current idle-screen overlay settings (logo/QR toggles + QR target)."""
        return background_manager.get_overlay_settings()

    @router.post("/background/overlays")
    async def set_background_overlays(request: StaticOverlayRequest):
        """Toggle the idle-screen logo/QR overlays (persisted across restarts)."""
        try:
            return await background_manager.set_overlay_settings(
                show_logo=request.show_logo,
                show_qr=request.show_qr,
                qr_url=request.qr_url,
                background_url=request.background_url,
            )
        except Exception as e:
            logging.error(f"Failed to set background overlays: {e}")
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

    @router.post("/display/navigate")
    async def navigate_display(request: dict):
        """Navigate the web display to a different URL/mode

        Args:
            request: {"url": "now-playing", "static", or a full URL (http/https)}
        """
        try:
            url_mode = request.get("url", "static")

            if url_mode == "now-playing":
                success = await background_manager.switch_to_now_playing()
            elif url_mode == "static":
                success = await background_manager.switch_to_static()
            elif url_mode.startswith(("http://", "https://")):
                success = await background_manager.switch_to_url(url_mode)
            else:
                raise HTTPException(status_code=400, detail=f"Invalid URL: {url_mode}. Use 'now-playing', 'static', or a full http(s) URL.")

            if success:
                return {"status": "success", "url": url_mode}
            else:
                raise HTTPException(status_code=500, detail="Failed to switch display mode")
        except Exception as e:
            logging.error(f"Failed to navigate display: {e}")
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
    display_detector=None
) -> APIRouter:
    """
    Setup system routes with dependency injection

    Args:
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
            "version": "4.0.0-all-react",
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
        return load_media_sources()

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
        from config import DEVICE_NAME
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


# =============================================================================
# WEBSOCKET ROUTES (for real-time events)
# =============================================================================

def setup_websocket_routes(
    websocket_manager: 'WebSocketManager',
    spotify_manager=None,
    display_ws_manager: 'WebSocketManager' = None,
    display_stack: 'DisplayStack' = None,
    audio_ws_manager: 'WebSocketManager' = None,
    audio_manager=None,
    sendspin_manager=None,
    bluetooth_manager=None,
) -> APIRouter:
    """
    Setup WebSocket routes for real-time event broadcasting

    Args:
        websocket_manager: WebSocketManager for Spotify/Sendspin events
        spotify_manager: SpotifyManager for initial state
        display_ws_manager: WebSocketManager for display state broadcasts
        display_stack: DisplayStack for initial display state
        audio_ws_manager: WebSocketManager for audio commands
        audio_manager: AudioManager for audio status updates from browser
        sendspin_manager: SendspinManager for initial state

    Returns:
        Configured APIRouter
    """
    from fastapi import WebSocket, WebSocketDisconnect
    import json
    router = APIRouter()

    def _current_track_initial_data():
        """Build the track_changed event for whichever source is active.

        Single builder for all now-playing sources so every client — kiosk or
        remote, fresh or reconnecting — hydrates from the same state the same
        way. The managers all keep track_info in the same shape.
        """
        for manager in (spotify_manager, sendspin_manager, bluetooth_manager):
            if not (manager and manager.is_playing):
                continue
            info = manager.track_info or {}
            if not info.get("name"):
                continue
            artists = info.get("artists", "Unknown Artist")
            if isinstance(artists, str):
                artists = artists.replace('\n', ', ')
            return {
                "event": "track_changed",
                "data": {
                    "name": info.get("name"),
                    "artists": artists,
                    "album": info.get("album", ""),
                    "album_art_url": info.get("album_art_url"),
                    "duration_ms": info.get("duration_ms", 0),
                    "spotify_url": info.get("spotify_url"),
                },
            }
        # A radio stream is playing — replay its card so a freshly-connected
        # client isn't blank. Carries the live track (SomaFM etc.) when the
        # stream provides metadata, otherwise just the station name.
        if audio_manager and (audio_payload := audio_manager.now_playing_payload()):
            return {
                "event": "track_changed",
                "data": audio_payload,
            }
        return None

    @router.websocket("/ws/now-playing")
    @router.websocket("/ws/spotify-events")  # deprecated alias (carries all sources)
    async def now_playing_websocket(websocket: WebSocket):
        """WebSocket endpoint for real-time now-playing track updates from any
        source (Spotify, Sendspin, Bluetooth, radio streams)."""
        # Send initial track data from whichever source is active
        await websocket_manager.connect(websocket, _current_track_initial_data())
        try:
            while True:
                data = await websocket.receive_text()
                logging.debug(f"Received WebSocket message: {data}")
                if data == "ping":
                    await websocket.send_text("pong")
        except WebSocketDisconnect:
            logging.info("WebSocket client disconnected")
        except Exception as e:
            logging.error(f"WebSocket error: {e}")
        finally:
            await websocket_manager.disconnect(websocket)

    @router.websocket("/ws/spotify-state")
    async def spotify_state_websocket(websocket: WebSocket):
        """WebSocket endpoint for Spotify playing/paused state changes"""
        initial_data = {
            "event": "spotify_state",
            "data": {
                "is_playing": spotify_manager.is_playing if spotify_manager else False
            }
        }

        await websocket_manager.connect(websocket, initial_data)
        try:
            while True:
                data = await websocket.receive_text()
        except WebSocketDisconnect:
            logging.info("Spotify state WebSocket disconnected")
        except Exception as e:
            logging.error(f"Spotify state WebSocket error: {e}")
        finally:
            await websocket_manager.disconnect(websocket)

    @router.websocket("/ws/display")
    async def display_websocket(websocket: WebSocket):
        """WebSocket endpoint for display state changes.

        On connect: sends current display item.
        On change: broadcasts new display item to all clients.
        """
        # Send current display state immediately — same shape as live
        # broadcasts (including the stack), stamped with the server's current
        # canvas build so a fresh client renders exactly what an always-connected
        # one does and an older bundle reloads itself (kiosks have no keyboard).
        initial_data = None
        if display_stack:
            from main import current_canvas_build  # lazy: avoids circular import
            payload = display_stack.current.to_dict()
            payload["stack"] = display_stack.get_stack()
            payload["app_build"] = current_canvas_build()
            initial_data = {
                "event": "display_state",
                "data": payload
            }


        await display_ws_manager.connect(websocket, initial_data)
        try:
            while True:
                data = await websocket.receive_text()
                if data == "ping":
                    await websocket.send_text("pong")
        except WebSocketDisconnect:
            logging.info("Display WebSocket client disconnected")
        except Exception as e:
            logging.error(f"Display WebSocket error: {e}")
        finally:
            await display_ws_manager.disconnect(websocket)

    @router.post("/display/reload-clients")
    async def reload_display_clients():
        """Tell every connected canvas to reload its page. Used to push a fresh
        bundle to input-less kiosks without touching them.

        Distinct from POST /display/reload (CDP kiosk reload): this reaches every
        connected screen (kiosk + remote mirrors) via the WebSocket reload event."""
        await display_ws_manager.broadcast("reload", {})
        return {"message": "Reload sent to display clients"}

    @router.websocket("/ws/audio")
    async def audio_websocket(websocket: WebSocket):
        """WebSocket endpoint for audio commands (backend -> browser) and status (browser -> backend).

        Backend sends: audio_play, audio_stop, audio_volume, audio_pause
        Browser sends: audio_status (periodic state reports)
        """
        # Send current audio state on connect
        initial_data = None
        if audio_manager and audio_manager.current_audio_stream:
            initial_data = {
                "type": "audio_play",
                "url": audio_manager.current_audio_stream,
                "volume": audio_manager.audio_volume,
            }

        await audio_ws_manager.connect(websocket, initial_data)
        try:
            while True:
                data = await websocket.receive_text()
                try:
                    msg = json.loads(data)
                    if msg.get("type") == "audio_status" and audio_manager:
                        audio_manager.handle_browser_status(msg)
                    elif msg.get("type") == "audio_ended" and audio_manager:
                        await audio_manager.handle_browser_ended(msg.get("src", ""))
                except json.JSONDecodeError:
                    if data == "ping":
                        await websocket.send_text("pong")
        except WebSocketDisconnect:
            logging.info("Audio WebSocket client disconnected")
        except Exception as e:
            logging.error(f"Audio WebSocket error: {e}")
        finally:
            await audio_ws_manager.disconnect(websocket)

    @router.get("/ws/status")
    async def websocket_status():
        """Get WebSocket connection status"""
        return {
            "spotify_events": websocket_manager.get_connection_count(),
            "display": display_ws_manager.get_connection_count() if display_ws_manager else 0,
            "audio": audio_ws_manager.get_connection_count() if audio_ws_manager else 0,
        }

    return router


# =============================================================================
# HOME ASSISTANT ROUTES
# =============================================================================

def setup_homeassistant_routes(ha_manager: 'HomeAssistantManager') -> APIRouter:
    """
    Setup Home Assistant integration routes

    Args:
        ha_manager: HomeAssistantManager instance

    Returns:
        Configured APIRouter
    """
    router = APIRouter()

    @router.get("/ha/status")
    async def get_ha_status():
        """Get Home Assistant integration status"""
        return ha_manager.get_status()

    @router.get("/ha/config")
    async def get_ha_config():
        """Get Home Assistant configuration (token masked)"""
        return ha_manager.get_config()

    @router.put("/ha/config")
    async def update_ha_config(request: HAConfigUpdateRequest):
        """Update Home Assistant connection settings"""
        return await ha_manager.update_config(
            ha_url=request.ha_url,
            ha_token=request.ha_token,
            entity_id=request.entity_id,
            enabled=request.enabled,
        )

    @router.post("/ha/test")
    async def test_ha_connection():
        """Test Home Assistant connection"""
        return await ha_manager.test_connection()

    @router.get("/ha/automations")
    async def get_ha_automations():
        """List all automation rules"""
        return {"automations": ha_manager.automations}

    @router.post("/ha/automations")
    async def add_ha_automations(request: HAAutomationAddRequest):
        """Add automation rules"""
        for rule in request.rules:
            ha_manager.automations.append(rule.model_dump())
        ha_manager._save_config()
        return {
            "message": f"Added {len(request.rules)} rule(s)",
            "automations": ha_manager.automations,
        }

    @router.delete("/ha/automations/{index}")
    async def delete_ha_automation(index: int):
        """Remove an automation rule by index"""
        if index < 0 or index >= len(ha_manager.automations):
            raise HTTPException(status_code=404, detail=f"Automation index {index} not found")
        removed = ha_manager.automations.pop(index)
        ha_manager._save_config()
        return {
            "message": f"Removed automation rule",
            "removed": removed,
            "automations": ha_manager.automations,
        }

    @router.post("/ha/push-state")
    async def force_push_state():
        """Force immediate state push to Home Assistant"""
        if not ha_manager.enabled:
            raise HTTPException(status_code=400, detail="HA integration not enabled")
        await ha_manager.notify_state_change()
        return {
            "message": "State pushed",
            "state": ha_manager._last_pushed_state,
        }

    @router.post("/ha/script/{script_id}")
    async def trigger_ha_script(script_id: str):
        """Trigger a Home Assistant script by ID"""
        if not ha_manager.ha_url or not ha_manager.ha_token:
            raise HTTPException(status_code=400, detail="HA not configured")
        await ha_manager.call_ha_script(script_id)
        return {"message": f"Script '{script_id}' triggered"}

    return router


# =============================================================================
# SENDSPIN ROUTES
# =============================================================================

def setup_sendspin_routes(sendspin_manager) -> APIRouter:
    """
    Setup Sendspin protocol routes

    Args:
        sendspin_manager: SendspinManager instance

    Returns:
        Configured APIRouter
    """
    router = APIRouter(prefix="/sendspin", tags=["sendspin"])

    @router.get("/status")
    async def get_sendspin_status():
        """Get Sendspin connection and playback status"""
        return sendspin_manager.get_status()

    @router.post("/hook/start")
    async def sendspin_hook_start():
        """Called by sendspin daemon --hook-start when audio stream starts."""
        await sendspin_manager.handle_hook_start()
        return {"status": "ok"}

    @router.post("/hook/stop")
    async def sendspin_hook_stop():
        """Called by sendspin daemon --hook-stop when audio stream stops."""
        await sendspin_manager.handle_hook_stop()
        return {"status": "ok"}

    @router.get("/artwork")
    async def get_sendspin_artwork():
        """Serve the latest album art received from Music Assistant via the
        Sendspin ARTWORK display client (binary frames over the LAN, no external
        URL). Cache-busted by the ?v= version in the broadcast art URL."""
        client = getattr(sendspin_manager, "artwork_client", None)
        if client is None or not client.art_bytes:
            raise HTTPException(status_code=404, detail="No artwork available")
        return Response(
            content=client.art_bytes,
            media_type=client.art_mime,
            headers={"Cache-Control": "no-cache"},
        )

    return router


# =============================================================================
# BLUETOOTH ROUTES
# =============================================================================

def setup_bluetooth_routes(bluetooth_manager) -> APIRouter:
    """
    Setup Bluetooth A2DP routes.

    Args:
        bluetooth_manager: BluetoothManager instance

    Returns:
        Configured APIRouter
    """
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


# =============================================================================
# DISPLAY STACK ROUTES (unified display management)
# =============================================================================

def setup_display_stack_routes(display_stack: 'DisplayStack', chromium_manager=None) -> APIRouter:
    """
    Setup display stack API routes for pushing/removing display items.

    Args:
        display_stack: DisplayStack instance

    Returns:
        Configured APIRouter
    """
    from models.request_models import DisplayPushRequest, WebsiteDisplayRequest, VideoDisplayRequest
    router = APIRouter()

    @router.post("/display/push")
    async def push_display_item(request: DisplayPushRequest):
        """Push a generic display item onto the stack"""
        item = await display_stack.push(
            request.type,
            request.content,
            duration=request.duration,
            item_id=request.item_id,
        )
        return {"message": f"Pushed {request.type} to display stack", "item": item.to_dict()}

    @router.post("/display/website")
    async def push_website(request: WebsiteDisplayRequest):
        """Push a website URL onto the display stack"""
        content = {"url": request.url}
        if request.zoom:
            content["zoom"] = request.zoom
        item = await display_stack.push("website", content, duration=request.duration)
        return {"message": f"Displaying website: {request.url}", "item": item.to_dict()}

    @router.post("/display/video")
    async def push_video(request: VideoDisplayRequest):
        """Push a video URL onto the display stack"""
        content = {"video_url": request.video_url}
        if request.mute is not None:
            content["mute"] = request.mute
        item = await display_stack.push("video", content, duration=request.duration)
        return {"message": f"Displaying video: {request.video_url}", "item": item.to_dict()}

    @router.get("/display/stack")
    async def get_display_stack():
        """Get the current display stack state"""
        return {
            "current": display_stack.current.to_dict(),
            "stack": display_stack.get_stack(),
        }

    @router.delete("/display/clear")
    async def clear_display_stack():
        """Clear all items from the display stack (back to static background)"""
        await display_stack.clear()
        return {"message": "Display stack cleared", "current": display_stack.current.to_dict()}

    @router.delete("/display/{item_id}")
    async def remove_display_item(item_id: str):
        """Remove a specific item from the display stack"""
        removed = await display_stack.remove(item_id)
        if removed:
            return {"message": f"Removed item {item_id}", "current": display_stack.current.to_dict()}
        else:
            raise HTTPException(status_code=404, detail=f"Item {item_id} not found in stack")

    @router.post("/display/reload")
    async def reload_chromium():
        """Reload the Chromium kiosk page via Chrome DevTools Protocol"""
        if not chromium_manager:
            raise HTTPException(status_code=503, detail="Chromium manager not available")
        success = await chromium_manager.reload_page()
        if success:
            return {"message": "Page reloaded"}
        raise HTTPException(status_code=500, detail="Failed to reload page")

    @router.post("/display/navigate")
    async def navigate_chromium(url: str):
        """Navigate Chromium to a new URL via Chrome DevTools Protocol"""
        if not chromium_manager:
            raise HTTPException(status_code=503, detail="Chromium manager not available")
        success = await chromium_manager.navigate(url)
        if success:
            return {"message": f"Navigated to {url}"}
        raise HTTPException(status_code=500, detail="Failed to navigate")

    return router


def setup_kiosk_routes(websocket_manager, spotify_manager, sendspin_manager, bluetooth_manager, display_stack) -> APIRouter:
    """Routes for tiny external kiosk panels (e.g. 320x240 BPi display).

    GET /canvas/kiosk   — server-rendered HTML, current track baked in,
                          edge-to-edge 320x240, no JS, no live WebSocket.
                          Optimised for headless-chromium screenshotting.
    GET /canvas/events  — Server-Sent Events stream. Emits one event per
                          track change. Outbound HTTP only, NAT/firewall
                          friendly. Auto-reconnects via SSE protocol.
    """
    import asyncio
    import html as html_lib
    import json as json_lib
    from fastapi import Request
    from fastapi.responses import HTMLResponse, StreamingResponse

    router = APIRouter()

    def _current_track():
        """Pick the active source from the display stack and return a flat
        dict of {name, artists, album, album_art_url, source}. Falls back to
        the last-known Spotify state when nothing is on the stack."""
        try:
            current = display_stack.current
            top = (display_stack.get_stack() or [])
            top_type = top[-1]["type"] if top else current.type
        except Exception:
            top_type = "static"

        info = {}
        source = top_type
        if top_type == "spotify" and spotify_manager and spotify_manager.track_info:
            info = spotify_manager.track_info
        elif top_type == "sendspin" and sendspin_manager and getattr(sendspin_manager, "track_info", None):
            info = sendspin_manager.track_info
        elif top_type == "bluetooth" and bluetooth_manager and getattr(bluetooth_manager, "track_info", None):
            info = bluetooth_manager.track_info
            source = "bluetooth"
        else:
            # Idle — show the last known Spotify track if there is one
            if spotify_manager and spotify_manager.track_info:
                info = spotify_manager.track_info
                source = "spotify-idle"

        artists = info.get("artists") or info.get("artist") or ""
        if isinstance(artists, list):
            artists = ", ".join(artists)
        artists = artists.replace("\n", ", ")

        return {
            "name": info.get("name") or "",
            "artists": artists,
            "album": info.get("album") or "",
            "album_art_url": info.get("album_art_url") or info.get("cover") or "",
            "source": source,
        }

    @router.get("/canvas/kiosk", response_class=HTMLResponse)
    async def kiosk_view():
        """320×240 server-rendered now-playing snapshot. No JS, no WS."""
        t = _current_track()
        # Escape user-provided text for safe HTML embedding
        name = html_lib.escape(t["name"]) or "—"
        artists = html_lib.escape(t["artists"]) or ""
        album = html_lib.escape(t["album"]) or ""
        art = html_lib.escape(t["album_art_url"], quote=True)
        # If there's no album art, the <img> tag with empty src would 404 —
        # omit it entirely. Layout uses CSS grid so the text column expands.
        art_html = f'<img src="{art}" width="96" height="96" alt="">' if art else '<div class="art-placeholder"></div>'
        body = f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=320, initial-scale=1, user-scalable=no">
<title>HSG Canvas</title>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
html, body {{ width: 320px; height: 240px; background: #000; color: #fff;
              font-family: 'Inter', 'Helvetica', sans-serif; overflow: hidden; }}
.kiosk {{ display: grid; grid-template-columns: 96px 1fr; gap: 12px;
         padding: 12px; width: 320px; height: 240px; }}
.art img, .art-placeholder {{ width: 96px; height: 96px; background: #222;
                              display: block; image-rendering: pixelated; }}
.text {{ overflow: hidden; }}
.title {{ font-size: 22px; font-weight: 700; line-height: 1.1;
          overflow: hidden; text-overflow: ellipsis; display: -webkit-box;
          -webkit-line-clamp: 3; -webkit-box-orient: vertical; }}
.artist {{ font-size: 14px; color: #cfd8e3; margin-top: 6px;
           white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
.footer {{ position: absolute; left: 12px; bottom: 8px; right: 12px;
           font-size: 11px; color: #6a7280;
           white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
</style>
</head><body>
<div class="kiosk">
  <div class="art">{art_html}</div>
  <div class="text">
    <div class="title">{name}</div>
    <div class="artist">{artists}</div>
  </div>
  <div class="footer">{album}</div>
</div>
</body></html>"""
        # Disable any caching so the render is always fresh per fetch
        return HTMLResponse(content=body, headers={"Cache-Control": "no-store, no-cache, must-revalidate"})

    @router.get("/canvas/events")
    async def kiosk_events(request: Request):
        """SSE stream of track-change events.

        First event is the current state on connect, then one event per
        change. Auto-reconnect via the SSE `retry:` directive.
        """
        async def event_gen():
            queue: asyncio.Queue = asyncio.Queue(maxsize=4)
            websocket_manager.register_sse(queue)
            try:
                # Tell client to retry every 5 s on disconnect
                yield "retry: 5000\n\n"
                # Initial paint — current state
                initial = _current_track()
                yield f"event: track\ndata: {json_lib.dumps(initial)}\n\n"

                # Heartbeat every 30 s to keep proxies from killing the
                # connection. SSE comments (lines starting with ':') are
                # ignored by the client but reset idle timers.
                heartbeat = 30.0
                while True:
                    if await request.is_disconnected():
                        break
                    try:
                        event_type, data = await asyncio.wait_for(queue.get(), timeout=heartbeat)
                    except asyncio.TimeoutError:
                        yield ": ping\n\n"
                        continue
                    # Only forward the events the kiosk cares about
                    if event_type in ("track_changed", "playback_state", "playing", "paused"):
                        payload = _current_track()
                        yield f"event: track\ndata: {json_lib.dumps(payload)}\n\n"
            finally:
                websocket_manager.unregister_sse(queue)

        return StreamingResponse(
            event_gen(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-store",
                "X-Accel-Buffering": "no",  # disable proxy buffering
                "Connection": "keep-alive",
            },
        )

    return router
