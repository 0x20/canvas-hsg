"""
API Request Models

Pydantic models for API request validation.
"""
from typing import Optional
from pydantic import BaseModel, Field


class StreamStartRequest(BaseModel):
    source_url: str = Field(description="URL of the stream source")
    protocol: str = Field("rtmp", description="Streaming protocol (rtmp, http_flv, hls)")


class PlaybackStartRequest(BaseModel):
    player: str = Field("mpv", description="Media player to use")
    mode: str = Field("optimized", description="Playback mode")
    protocol: str = Field("rtmp", description="Streaming protocol")


class ImageDisplayRequest(BaseModel):
    image_data: str = Field(description="Base64 encoded image data")
    duration: int = Field(10, gt=0, le=3600, description="Seconds to display (1-3600)")


class YoutubePlayRequest(BaseModel):
    youtube_url: str = Field(description="YouTube video URL")
    duration: Optional[int] = Field(None, gt=0, le=86400, description="Playback duration in seconds (max 24h)")
    mute: Optional[bool] = Field(False, description="If true, play without audio")
    youtube_quality: Optional[str] = Field(None, description="Video quality preference (e.g., '1080p', '720p')")


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


class CastReceiveRequest(BaseModel):
    media_url: str = Field(description="URL of the media to receive")
    content_type: Optional[str] = Field(None, description="MIME type of content")
    title: Optional[str] = Field(None, description="Display title")


class SpotifyEventRequest(BaseModel):
    event: str = Field(description="Event type: session_connected, playing, paused, stopped, volume_set, etc.")
    track_id: Optional[str] = Field(None, description="Spotify track ID")
    old_track_id: Optional[str] = Field(None, description="Previous track ID")
    duration_ms: Optional[int] = Field(None, ge=0, description="Track duration in milliseconds")
    position_ms: Optional[int] = Field(None, ge=0, description="Current position in milliseconds")


# New models for routes that previously used raw dicts or request.json()

class PlaybackVolumeRequest(BaseModel):
    volume: int = Field(ge=0, le=130, description="Playback volume 0-130")


class BackgroundModeRequest(BaseModel):
    mode: str = Field(description="Background display mode (currently only 'static')")


class SpotifyVolumeRequest(BaseModel):
    volume: int = Field(70, ge=0, le=100, description="Spotify volume 0-100")


class WebcastStartRequest(BaseModel):
    url: str = Field(description="URL of the website to webcast")
    viewport_width: int = Field(1920, gt=0, description="Viewport width in pixels")
    viewport_height: int = Field(1080, gt=0, description="Viewport height in pixels")
    scroll_delay: float = Field(5.0, gt=0, description="Delay between scrolls in seconds")
    scroll_percentage: float = Field(30.0, gt=0, le=100, description="Percentage of page to scroll each step")
    overlap_percentage: float = Field(5.0, ge=0, le=50, description="Overlap percentage between scroll steps")
    loop_count: int = Field(3, ge=0, description="Number of scroll loops (0 = infinite)")
    zoom_level: float = Field(1.0, gt=0, le=5.0, description="Page zoom level")
    wait_for_load: float = Field(3.0, ge=0, description="Seconds to wait for page load")
    screenshot_path: str = Field("/tmp/webcast_screenshot.png", description="Path for webcast screenshots")


class WebcastConfigRequest(BaseModel):
    scroll_delay: Optional[float] = Field(None, gt=0, description="Delay between scrolls")
    scroll_percentage: Optional[float] = Field(None, gt=0, le=100, description="Scroll percentage")
    overlap_percentage: Optional[float] = Field(None, ge=0, le=50, description="Overlap percentage")
    loop_count: Optional[int] = Field(None, ge=0, description="Number of loops")
    zoom_level: Optional[float] = Field(None, gt=0, le=5.0, description="Zoom level")


class WebcastScrollRequest(BaseModel):
    direction: str = Field("down", description="Scroll direction ('up' or 'down')")
    amount: Optional[float] = Field(None, gt=0, description="Scroll amount in pixels")


class WebcastJumpRequest(BaseModel):
    position_percent: float = Field(0, ge=0, le=100, description="Position to jump to as percentage")
