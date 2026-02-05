"""
Shared media type detection utilities.

Used by ChromecastManager and CastReceiverManager.
"""
from urllib.parse import urlparse


def detect_media_type(media_url: str, content_type: str = None) -> str:
    """
    Detect if media URL is audio or video based on content type, file extension, and URL patterns.

    Args:
        media_url: Media URL to analyze
        content_type: Optional MIME type hint (e.g. 'video/mp4')

    Returns:
        'audio' or 'video'
    """
    # Check content type first (if provided)
    if content_type:
        if 'video' in content_type.lower():
            return 'video'
        if 'audio' in content_type.lower():
            return 'audio'

    # Parse URL
    parsed = urlparse(media_url.lower())
    path = parsed.path

    # Check for video services
    if 'youtube.com' in parsed.netloc or 'youtu.be' in parsed.netloc:
        return 'video'
    if 'vimeo.com' in parsed.netloc:
        return 'video'

    # Common audio file extensions
    audio_extensions = ['.mp3', '.m4a', '.aac', '.ogg', '.opus', '.flac', '.wav', '.wma']
    # Common video file extensions
    video_extensions = ['.mp4', '.mkv', '.webm', '.avi', '.mov', '.m4v', '.flv', '.wmv']

    # Check file extension
    for ext in audio_extensions:
        if path.endswith(ext):
            return 'audio'

    for ext in video_extensions:
        if path.endswith(ext):
            return 'video'

    # Check for streaming patterns
    if any(pattern in media_url.lower() for pattern in ['.pls', '.m3u', 'radio', 'somafm', 'stream', 'audio']):
        return 'audio'

    if any(pattern in media_url.lower() for pattern in ['youtube', 'youtu.be', 'vimeo', 'video']):
        return 'video'

    # Default to video for unknown types
    return 'video'
