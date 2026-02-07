# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

HSG Canvas (Hackerspace.gent Canvas) - a FastAPI application that manages media streaming and playback on a Raspberry Pi. Runs alongside an SRS (Simple Realtime Server) to display streams, images, and YouTube content on a connected display. The Pi acts as both a media player and a stream republisher.

## Development Commands

```bash
# Install dependencies
pip3 install -r requirements.txt

# Run server (development, port 8000)
python3 main.py

# Run server (production, port 80)
sudo python3 main.py --production

# Run via start script (kills orphan mpv processes, sets AUDIO_DEVICE, runs production)
./start.sh

# Run tests
pytest tests/

# Run a single test file
pytest tests/test_mpv_pools.py

# Run with verbose output
pytest tests/test_mpv_pools.py -v
```

## Architecture

### Application Wiring

`main.py` uses FastAPI's lifespan context manager to initialize everything in order:

1. **DisplayCapabilityDetector** - detects connected display resolution via DRM
2. **FramebufferManager** - direct framebuffer access (mostly legacy)
3. **AudioMPVPool** (size=2) and **VideoMPVPool** (size=1) - persistent mpv processes with IPC sockets
4. **BackgroundManager** - shows default background image on startup
5. **All other managers** - each receives its dependencies via constructor injection
6. **API routes** - each `setup_*_routes()` function creates an `APIRouter` with manager references
7. **Health monitor** - background asyncio task checking pool health every 30s

Shutdown reverses this order. All managers are global module-level variables set during lifespan.

### Key Directories

- **`managers/`** - All business logic including MPV pools, controllers, and health monitoring (there is no separate `core/` directory)
- **`models/`** - Pydantic request models (`request_models.py`)
- **`routes.py`** - Single file with 12 `setup_*_routes()` functions, each returning an `APIRouter`
- **`config.py`** - All constants: SRS URLs, pool sizes, player command matrix, paths
- **`background_engine/`** - Advanced background image generation (layout, components, generators)
- **`tests/`** - pytest tests with pytest-asyncio for async testing
- **`static/`** - CSS/JS for the web interface
- **`index.html`** - Synthwave-themed web control panel (served at `/`)

### MPV Pool System (`managers/mpv_pools.py`, `managers/mpv_controller.py`)

The core playback infrastructure. MPV processes are long-lived and controlled via JSON IPC over Unix sockets in `/tmp/`:

- **MPVProcessPool** (base) → **AudioMPVPool** (audio-only, no video output) and **VideoMPVPool** (DRM output, hardware decoding)
- Each pool manages N mpv subprocesses, tracks which controllers are available
- **MPVController** handles async socket communication: `loadfile`, `set_property`, `get_property`, pause/seek
- Health monitor (`managers/health_monitor.py`) auto-restarts crashed processes

### Manager Interactions

Managers reference each other for coordinated behavior:
- **PlaybackManager** depends on: VideoMPVPool, DisplayCapabilityDetector, BackgroundManager, AudioManager
- **ChromecastManager** depends on: AudioManager, PlaybackManager (stops local playback when casting)
- **CastReceiverManager** depends on: PlaybackManager, AudioManager (routes received casts)
- **OutputTargetManager** depends on: AudioManager, PlaybackManager, ChromecastManager (unified target interface)
- **SpotifyManager** depends on: AudioManager (stops audio streams when Spotify plays)
- **BackgroundManager** depends on: DisplayCapabilityDetector, FramebufferManager, VideoMPVPool

### Route Pattern

Each route group in `routes.py` follows the same pattern:
```python
def setup_X_routes(manager, ...) -> APIRouter:
    router = APIRouter(prefix="/X", tags=["X"])
    # Endpoint definitions using the injected manager
    return router
```

Routes are included in the app during lifespan startup via `app.include_router()`.

## Configuration (`config.py`)

- **SRS URLs**: RTMP on `localhost:1935`, HTTP-FLV/HLS on `localhost:8080`, API on `localhost:1985`
- **AUDIO_DEVICE**: Defaults to `pulse` (PipeWire), overridable via environment variable
- **Pool sizes**: Audio=2, Video=1
- **OPTIMAL_PLAYER_COMMANDS**: Resolution-specific mpv/ffplay/vlc command arrays with hardware acceleration flags

## Hardware Context

This runs on a Raspberry Pi with:
- DRM/KMS display output (no X11 in production)
- v4l2m2m hardware video decoding
- PipeWire/PulseAudio for audio (shared with Raspotify service)
- Temperature monitoring via `/sys/class/thermal/thermal_zone0/temp`
- HDMI-CEC for TV power control
- yt-dlp with Deno runtime for YouTube extraction (PATH includes `~/.deno/bin`)

## Important Patterns

- **Subprocess isolation**: Chromecast discovery runs in a subprocess to prevent zeroconf file descriptor leaks
- **Process cleanup**: `os.setsid()` used for FFmpeg/player processes so entire process groups can be killed
- **YouTube codec preference**: H.264 (AVC1) preferred over VP9 for Pi hardware decoding
- **Audio exclusivity**: Only one audio source at a time (audio stream, Spotify, or video with audio)
- **Background restoration**: After playback/image display ends, background image is automatically restored
