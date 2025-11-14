"""
HSG Canvas Configuration

Central configuration file for all constants and settings.
"""
import os

# SRS Server Configuration
HOST = "localhost"
SRS_RTMP_URL = f"rtmp://{HOST}:1935/live"
SRS_HTTP_FLV_URL = f"http://{HOST}:8080/live"
SRS_HLS_URL = f"http://{HOST}:8080/live"
SRS_API_URL = f"http://{HOST}:1985/api/v1"

# Audio Configuration
# Use pulse (PipeWire) instead of direct ALSA to avoid conflicts with Raspotify
AUDIO_DEVICE = os.getenv("AUDIO_DEVICE", "pulse")

# Paths
DEFAULT_BACKGROUND_PATH = "/home/hsg/srs_server/canvas_background.png"
TEMP_IMAGE_DIR = "/tmp/stream_images"
SOCKET_DIR = "/tmp"

# MPV Pool Configuration
AUDIO_POOL_SIZE = 2
VIDEO_POOL_SIZE = 1

# Health Monitor Configuration
HEALTH_CHECK_INTERVAL = 30  # seconds

# Server Configuration
DEFAULT_PORT = 8000
PRODUCTION_PORT = 80

# Explicit player command matrix for all resolutions
OPTIMAL_PLAYER_COMMANDS = {
    # 4K UHD Commands - Optimized for smooth playback
    "mpv_3840x2160_60hz": [
        "mpv", "--vo=drm", "--drm-mode=3840x2160@60", "--fs", "--quiet",
        "--no-input-default-bindings", "--no-osc", "--hwdec=v4l2m2m",
        "--vd-lavc-threads=4", "--cache=yes", "--demuxer-max-bytes=50MiB",
        "--cache-secs=3", "--vd-lavc-dr=yes", "--vd-lavc-fast",
        f"--audio-device={AUDIO_DEVICE}"
    ],
    "mpv_3840x2160_30hz": [
        "mpv", "--vo=drm", "--drm-mode=3840x2160@30", "--fs", "--quiet",
        "--no-input-default-bindings", "--no-osc", "--hwdec=v4l2m2m",
        "--vd-lavc-threads=4", "--cache=yes", "--demuxer-max-bytes=50MiB",
        "--cache-secs=3", "--vd-lavc-dr=yes", "--vd-lavc-fast",
        f"--audio-device={AUDIO_DEVICE}"
    ],

    # 1440p Commands
    "mpv_2560x1440_144hz": [
        "mpv", "--vo=drm", "--drm-mode=2560x1440@144", "--fs", "--quiet",
        "--no-input-default-bindings", "--no-osc", "--hwdec=v4l2m2m",
        "--vd-lavc-fast", "--cache=yes", "--cache-secs=2",
        f"--audio-device={AUDIO_DEVICE}"
    ],
    "mpv_2560x1440_120hz": [
        "mpv", "--vo=drm", "--drm-mode=2560x1440@120", "--fs", "--quiet",
        "--no-input-default-bindings", "--no-osc", "--hwdec=v4l2m2m",
        f"--audio-device={AUDIO_DEVICE}"
    ],
    "mpv_2560x1440_60hz": [
        "mpv", "--vo=drm", "--drm-mode=2560x1440@60", "--fs", "--quiet",
        "--no-input-default-bindings", "--no-osc", "--hwdec=v4l2m2m",
        f"--audio-device={AUDIO_DEVICE}"
    ],

    # 1080p Commands
    "mpv_1920x1080_144hz": [
        "mpv", "--vo=drm", "--drm-mode=1920x1080@144", "--fs", "--quiet",
        "--no-input-default-bindings", "--no-osc", "--hwdec=v4l2m2m",
        "--vd-lavc-fast", "--cache=yes", "--cache-secs=2",
        f"--audio-device={AUDIO_DEVICE}"
    ],
    "mpv_1920x1080_120hz": [
        "mpv", "--vo=drm", "--drm-mode=1920x1080@120", "--fs", "--quiet",
        "--no-input-default-bindings", "--no-osc", "--hwdec=v4l2m2m",
        f"--audio-device={AUDIO_DEVICE}"
    ],
    "mpv_1920x1080_60hz": [
        "mpv", "--vo=drm", "--drm-mode=1920x1080@60", "--fs", "--quiet",
        "--no-input-default-bindings", "--no-osc", "--hwdec=v4l2m2m",
        "--ao=pulse", "--audio-channels=stereo",
        f"--audio-device={AUDIO_DEVICE}"
    ],

    # 720p Commands
    "mpv_1280x720_120hz": [
        "mpv", "--vo=drm", "--drm-mode=1280x720@120", "--fs", "--quiet",
        "--no-input-default-bindings", "--no-osc", "--hwdec=v4l2m2m",
        f"--audio-device={AUDIO_DEVICE}"
    ],
    "mpv_1280x720_60hz": [
        "mpv", "--vo=drm", "--drm-mode=1280x720@60", "--fs", "--quiet",
        "--no-input-default-bindings", "--no-osc", "--hwdec=v4l2m2m",
        "--ao=pulse", "--audio-channels=stereo",
        f"--audio-device={AUDIO_DEVICE}"
    ],

    # XGA Commands
    "mpv_1024x768_75hz": [
        "mpv", "--vo=drm", "--drm-mode=1024x768@75", "--fs", "--quiet",
        "--no-input-default-bindings", "--no-osc", "--hwdec=v4l2m2m",
        f"--audio-device={AUDIO_DEVICE}"
    ],
    "mpv_1024x768_60hz": [
        "mpv", "--vo=drm", "--drm-mode=1024x768@60", "--fs", "--quiet",
        "--no-input-default-bindings", "--no-osc", "--hwdec=v4l2m2m",
        "--ao=pulse", "--audio-channels=stereo",
        f"--audio-device={AUDIO_DEVICE}"
    ],

    # SVGA Commands
    "mpv_800x600_75hz": [
        "mpv", "--vo=drm", "--drm-mode=800x600@75", "--fs", "--quiet",
        "--no-input-default-bindings", "--no-osc", "--hwdec=v4l2m2m",
        f"--audio-device={AUDIO_DEVICE}"
    ],
    "mpv_800x600_60hz": [
        "mpv", "--vo=drm", "--drm-mode=800x600@60", "--fs", "--quiet",
        "--no-input-default-bindings", "--no-osc", "--hwdec=v4l2m2m",
        "--ao=pulse", "--audio-channels=stereo",
        f"--audio-device={AUDIO_DEVICE}"
    ],

    # VGA Fallback Commands
    "mpv_640x480_60hz": [
        "mpv", "--vo=drm", "--drm-mode=640x480@60", "--fs", "--quiet",
        "--no-input-default-bindings", "--no-osc",
        f"--audio-device={AUDIO_DEVICE}"
    ],

    # FFplay Variants
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

    # VLC Variants
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

    # Legacy compatibility commands
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
    "vlc_basic": ["vlc", "--intf", "dummy", "--fullscreen"]
}

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
