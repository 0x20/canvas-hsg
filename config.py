"""
HSG Canvas Configuration

Central configuration file for all constants and settings.
"""
import os

# SRS Server Configuration
HOST = os.getenv("SRS_HOST", "localhost")
SRS_RTMP_URL = f"rtmp://{HOST}:1935/live"
SRS_HTTP_FLV_URL = f"http://{HOST}:8080/live"
SRS_HLS_URL = f"http://{HOST}:8080/live"
SRS_API_URL = f"http://{HOST}:1985/api/v1"

# Audio Configuration
# Use pulse (PipeWire) instead of direct ALSA to avoid conflicts with Raspotify
AUDIO_DEVICE = os.getenv("AUDIO_DEVICE", "pulse")

# Base directory (for resolving relative paths)
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Paths
DEFAULT_BACKGROUND_PATH = os.path.join(_BASE_DIR, "canvas_background.png")
YOUTUBE_COOKIES_PATH = os.path.join(_BASE_DIR, "youtube-cookies.txt")
TEMP_IMAGE_DIR = "/tmp/stream_images"
SOCKET_DIR = "/tmp"

# MPV Pool Configuration
AUDIO_POOL_SIZE = 2
VIDEO_POOL_SIZE = 1

# Health Monitor Configuration
HEALTH_CHECK_INTERVAL = 30  # seconds

# Network/Discovery Constants
SSDP_MULTICAST_ADDR = "239.255.255.250"
SSDP_PORT = 1900
DEVICE_NAME = "HSG Canvas"
CHROMECAST_CACHE_DURATION = 86400  # 24 hours
METADATA_UPDATE_INTERVAL = 15  # seconds

# Server Configuration
DEFAULT_PORT = 8000
PRODUCTION_PORT = 80

# Player command generation
def _build_mpv_command(drm_mode: str, extra_flags: list = None, hwdec: bool = True) -> list:
    """Build an mpv command with standard DRM flags."""
    cmd = ["mpv", "--vo=drm", f"--drm-mode={drm_mode}", "--fs", "--quiet",
           "--no-input-default-bindings", "--no-osc"]
    if hwdec:
        cmd.append("--hwdec=v4l2m2m")
    if extra_flags:
        cmd.extend(extra_flags)
    cmd.append(f"--audio-device={AUDIO_DEVICE}")
    return cmd


# Resolution definitions: (resolution, refresh, extra_flags, hwdec)
_4K_PERF = ["--vd-lavc-threads=4", "--cache=yes", "--demuxer-max-bytes=50MiB",
            "--cache-secs=3", "--vd-lavc-dr=yes", "--vd-lavc-fast"]
_HIGH_REFRESH_PERF = ["--vd-lavc-fast", "--cache=yes", "--cache-secs=2"]
_60HZ_AUDIO = ["--ao=pulse", "--audio-channels=stereo"]

_MPV_RESOLUTIONS = [
    # (width, height, refresh, extra_flags, hwdec)
    (3840, 2160, 60,  _4K_PERF,           True),
    (3840, 2160, 30,  _4K_PERF,           True),
    (2560, 1440, 144, _HIGH_REFRESH_PERF, True),
    (2560, 1440, 120, None,               True),
    (2560, 1440, 60,  None,               True),
    (1920, 1080, 144, _HIGH_REFRESH_PERF, True),
    (1920, 1080, 120, None,               True),
    (1920, 1080, 60,  _60HZ_AUDIO,        True),
    (1280, 720,  120, None,               True),
    (1280, 720,  60,  _60HZ_AUDIO,        True),
    (1024, 768,  75,  None,               True),
    (1024, 768,  60,  _60HZ_AUDIO,        True),
    (800,  600,  75,  None,               True),
    (800,  600,  60,  _60HZ_AUDIO,        True),
    (640,  480,  60,  None,               False),  # No hwdec for VGA
]

# Generate mpv resolution commands from data
OPTIMAL_PLAYER_COMMANDS = {}
for _w, _h, _r, _extra, _hw in _MPV_RESOLUTIONS:
    _key = f"mpv_{_w}x{_h}_{_r}hz"
    OPTIMAL_PLAYER_COMMANDS[_key] = _build_mpv_command(f"{_w}x{_h}@{_r}", _extra, _hw)

# FFplay variants (few entries, not worth templating)
OPTIMAL_PLAYER_COMMANDS.update({
    "ffplay_3840x2160_60hz": [
        "ffplay", "-fs", "-autoexit", "-hwaccel", "v4l2m2m",
        "-video_size", "3840x2160", "-framerate", "60"
    ],
    "ffplay_1920x1080_60hz": [
        "ffplay", "-fs", "-autoexit", "-hwaccel", "v4l2m2m",
        "-video_size", "1920x1080", "-framerate", "60"
    ],
    "ffplay_1024x768_60hz": [
        "ffplay", "-fs", "-autoexit", "-hwaccel", "v4l2m2m",
        "-video_size", "1024x768", "-framerate", "60"
    ],
})

# VLC variants
OPTIMAL_PLAYER_COMMANDS.update({
    "vlc_3840x2160_60hz": [
        "vlc", "--intf", "dummy", "--fullscreen", "--avcodec-hw", "v4l2m2m",
        "--width", "3840", "--height", "2160"
    ],
    "vlc_1920x1080_60hz": [
        "vlc", "--intf", "dummy", "--fullscreen", "--avcodec-hw", "v4l2m2m",
        "--width", "1920", "--height", "1080"
    ],
    "vlc_1024x768_60hz": [
        "vlc", "--intf", "dummy", "--fullscreen", "--avcodec-hw", "v4l2m2m",
        "--width", "1024", "--height", "768"
    ],
})

# Legacy compatibility commands
OPTIMAL_PLAYER_COMMANDS.update({
    "mpv_basic": ["mpv", "--vo=drm", "--fs", "--quiet", f"--audio-device={AUDIO_DEVICE}"],
    "mpv_optimized": [
        "mpv", "--vo=drm", "--fs", "--quiet",
        "--no-input-default-bindings", "--no-osc", "--untimed",
        f"--audio-device={AUDIO_DEVICE}"
    ],
    "mpv_no_cache": [
        "mpv", "--vo=drm", "--fs", "--quiet", "--hwdec=v4l2m2m",
        "--no-input-default-bindings", "--no-osc", "--cache=no",
        f"--audio-device={AUDIO_DEVICE}"
    ],
    "ffplay_basic": ["ffplay", "-fs", "-autoexit"],
    "vlc_basic": ["vlc", "--intf", "dummy", "--fullscreen"],
})

# Legacy player commands for backward compatibility
PLAYER_COMMANDS = {
    "mpv": {
        "basic": OPTIMAL_PLAYER_COMMANDS["mpv_basic"],
        "optimized": OPTIMAL_PLAYER_COMMANDS["mpv_optimized"],
        "fullscreen": OPTIMAL_PLAYER_COMMANDS["mpv_optimized"],
        "drm": OPTIMAL_PLAYER_COMMANDS["mpv_optimized"],
        "auto_mode": OPTIMAL_PLAYER_COMMANDS["mpv_optimized"],
        "1024x768": OPTIMAL_PLAYER_COMMANDS["mpv_1024x768_60hz"],
        "800x600": OPTIMAL_PLAYER_COMMANDS["mpv_800x600_60hz"]
    },
    "ffplay": {
        "basic": OPTIMAL_PLAYER_COMMANDS["ffplay_basic"],
        "optimized": OPTIMAL_PLAYER_COMMANDS["ffplay_1024x768_60hz"],
        "fullscreen": OPTIMAL_PLAYER_COMMANDS["ffplay_1024x768_60hz"]
    },
    "vlc": {
        "basic": OPTIMAL_PLAYER_COMMANDS["vlc_basic"],
        "optimized": OPTIMAL_PLAYER_COMMANDS["vlc_1024x768_60hz"],
        "fullscreen": OPTIMAL_PLAYER_COMMANDS["vlc_1024x768_60hz"]
    }
}
