"""
API Request Models

Pydantic models for API request validation.
"""
from typing import Optional
from pydantic import BaseModel


class StreamStartRequest(BaseModel):
    source_url: str
    protocol: str = "rtmp"


class PlaybackStartRequest(BaseModel):
    player: str = "mpv"
    mode: str = "optimized"
    protocol: str = "rtmp"


class ImageDisplayRequest(BaseModel):
    image_data: str  # base64 encoded image
    duration: int = 10  # seconds to display


class YoutubePlayRequest(BaseModel):
    youtube_url: str
    duration: Optional[int] = None  # None = play full video
    mute: Optional[bool] = False  # True = no audio output


class QRCodeRequest(BaseModel):
    content: str  # URL or text to encode in QR code
    duration: Optional[int] = None  # seconds to display, None = forever


class AudioStreamRequest(BaseModel):
    stream_url: str
    volume: Optional[int] = None  # 0-100, None = use current setting


class AudioVolumeRequest(BaseModel):
    volume: int  # 0-100
