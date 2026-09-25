"""
API Request Models

Pydantic models for API request validation.
"""
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field


class ImageDisplayRequest(BaseModel):
    image_data: str = Field(description="Base64 encoded image data")
    duration: int = Field(10, gt=0, le=3600, description="Seconds to display (1-3600)")


class YoutubePlayRequest(BaseModel):
    youtube_url: str = Field(description="YouTube video URL")
    duration: Optional[int] = Field(None, gt=0, le=86400, description="Playback duration in seconds (max 24h)")
    mute: Optional[bool] = Field(False, description="If true, play without audio")
    youtube_quality: Optional[str] = Field(None, description="Video quality preference (e.g., '1080p', '720p')")


class TwitchPlayRequest(BaseModel):
    twitch_url: str = Field(description="Twitch channel, VOD, or clip URL")
    duration: Optional[int] = Field(None, gt=0, le=86400, description="Playback duration in seconds (max 24h)")
    mute: Optional[bool] = Field(False, description="If true, play without audio")


class QRCodeRequest(BaseModel):
    content: str = Field(description="URL or text to encode in QR code")
    duration: Optional[int] = Field(None, gt=0, le=3600, description="Seconds to display, None = forever")


class AudioStreamRequest(BaseModel):
    stream_url: str = Field(description="Audio stream URL")
    volume: Optional[int] = Field(None, ge=0, le=100, description="Volume level 0-100, None = use current setting")


class AudioVolumeRequest(BaseModel):
    volume: int = Field(ge=0, le=100, description="Volume level 0-100")


class ChromecastStartRequest(BaseModel):
    media_url: str = Field(description="URL of the media to cast")
    device_name: Optional[str] = Field(None, description="Chromecast device name, None = use first available")
    content_type: Optional[str] = Field(None, description="MIME type, None = auto-detect")
    title: Optional[str] = Field(None, description="Display title for the media")


class ChromecastVolumeRequest(BaseModel):
    volume: float = Field(ge=0.0, le=1.0, description="Chromecast volume 0.0-1.0")


class SpotifyEventRequest(BaseModel):
    event: str = Field(description="Event type: session_connected, playing, paused, stopped, volume_set, etc.")
    track_id: Optional[str] = Field(None, description="Spotify track ID")
    old_track_id: Optional[str] = Field(None, description="Previous track ID")
    duration_ms: Optional[int] = Field(None, ge=0, description="Track duration in milliseconds")
    position_ms: Optional[int] = Field(None, ge=0, description="Current position in milliseconds")
    name: Optional[str] = Field(None, description="Track title (from librespot onevent)")
    artists: Optional[str] = Field(None, description="Comma-separated artist names (from librespot onevent)")
    album: Optional[str] = Field(None, description="Album name (from librespot onevent)")
    covers: Optional[str] = Field(None, description="Album art URL (from librespot onevent)")


# New models for routes that previously used raw dicts or request.json()

class PlaybackVolumeRequest(BaseModel):
    volume: int = Field(ge=0, le=130, description="Playback volume 0-130")


class BackgroundModeRequest(BaseModel):
    mode: str = Field(description="Background display mode (currently only 'static')")


class StaticOverlayRequest(BaseModel):
    """Toggle the idle-screen logo/QR overlays. All fields optional — only the
    provided ones are changed."""
    show_logo: Optional[bool] = Field(None, description="Show the hackerspace logo overlay")
    show_qr: Optional[bool] = Field(None, description="Show the QR-code overlay")
    qr_url: Optional[str] = Field(None, description="URL the QR code encodes")
    background_url: Optional[str] = Field(None, description="Idle background image URL")


class SpotifyVolumeRequest(BaseModel):
    volume: int = Field(70, ge=0, le=100, description="Spotify volume 0-100")


class HAConfigUpdateRequest(BaseModel):
    ha_url: Optional[str] = Field(None, description="Home Assistant URL (e.g., http://192.168.1.100:8123)")
    ha_token: Optional[str] = Field(None, description="Long-Lived Access Token")
    entity_id: Optional[str] = Field(None, description="HA entity ID for this canvas")
    enabled: Optional[bool] = Field(None, description="Enable/disable the integration")


class HAAutomationRule(BaseModel):
    trigger_entity: str = Field(description="HA entity ID to watch (e.g., binary_sensor.motion)")
    trigger_from: Optional[str] = Field(None, description="Trigger only when old state matches")
    trigger_to: Optional[str] = Field(None, description="Trigger only when new state matches")
    action: str = Field(description="Action to execute (e.g., cec.tv_power_on, audio.start)")
    action_args: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Arguments for the action")


class HAAutomationAddRequest(BaseModel):
    rules: List[HAAutomationRule] = Field(description="List of automation rules to add")


# Display Stack models

class DisplayPushRequest(BaseModel):
    type: str = Field(description="Display type: static, spotify, image, qrcode, youtube, website, video")
    content: Dict[str, Any] = Field(default_factory=dict, description="Type-specific content dict")
    duration: Optional[int] = Field(None, gt=0, le=86400, description="Auto-expire duration in seconds")
    item_id: Optional[str] = Field(None, description="Fixed item ID for idempotent pushes")


class WebsiteDisplayRequest(BaseModel):
    url: str = Field(description="Website URL to display")
    zoom: Optional[float] = Field(None, gt=0, le=5.0, description="CSS zoom level")
    duration: Optional[int] = Field(None, gt=0, le=86400, description="Auto-expire duration in seconds")


class VideoDisplayRequest(BaseModel):
    video_url: str = Field(description="Video file URL to display")
    mute: Optional[bool] = Field(False, description="Mute audio on the video")
    duration: Optional[int] = Field(None, gt=0, le=86400, description="Auto-expire duration in seconds")
