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

## Production Deployment (systemd)

HSG Canvas runs as a systemd service on the Raspberry Pi for automatic startup and management.

### Service Management

```bash
# Start/stop/restart the service
sudo systemctl start hsg-canvas
sudo systemctl stop hsg-canvas
sudo systemctl restart hsg-canvas

# Check service status
systemctl status hsg-canvas

# View service logs
sudo journalctl -u hsg-canvas -f          # Follow logs in real-time
sudo journalctl -u hsg-canvas -n 100      # Last 100 lines
sudo journalctl -u hsg-canvas --since today

# Enable/disable auto-start on boot
sudo systemctl enable hsg-canvas
sudo systemctl disable hsg-canvas
```

### Service Configuration

The service file is located at `/etc/systemd/system/hsg-canvas.service`:

```ini
[Unit]
Description=HSG Canvas - Media Streaming and Playback Manager
After=network.target srs-server.service
Wants=network-online.target srs-server.service

[Service]
Type=simple
User=hsg
Group=hsg
WorkingDirectory=/home/hsg/srs_server
ExecStart=/home/hsg/srs_server/start.sh
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
Environment=DISPLAY=:0
Environment=HOME=/home/hsg
Environment=XDG_RUNTIME_DIR=/run/user/1000

# Security settings (relaxed for media playback access)
AmbientCapabilities=CAP_NET_BIND_SERVICE
PrivateTmp=false

[Install]
WantedBy=multi-user.target
```

**Key Points**:
- Runs as user `hsg` (not root)
- Uses virtual environment via `start.sh`
- Auto-restarts on crash (10 second delay)
- Binds to port 80 via `CAP_NET_BIND_SERVICE` capability
- Logs to systemd journal

### Updating the Service

After making code changes:

```bash
# Restart the service to pick up changes
sudo systemctl restart hsg-canvas

# If you modified the service file itself
sudo systemctl daemon-reload
sudo systemctl restart hsg-canvas
```

## Web-Based Display System

**Status**: Implemented (February 2026)
**Phase**: 1 - Spotify Now-Playing View

The system uses **Chromium in kiosk mode** for modern, web-based display rendering instead of PIL/FFmpeg image/video generation.

### Architecture

```
Spotify Event (librespot)
    ↓
SpotifyManager → broadcasts via WebSocket
    ↓
WebSocketManager → pushes to all clients
    ↓
Now-Playing HTML Page (/now-playing)
    ↓
Chromium Kiosk Mode (Xvfb virtual display)
    ↓
Physical Display (HDMI output)
```

### Components

#### 1. WebSocket Infrastructure (`managers/websocket_manager.py`)
- Real-time event broadcasting to connected clients
- Endpoint: `ws://localhost/ws/spotify-events`
- Status: `GET /ws/status` → returns active connection count
- Events: `track_changed`, `playback_state`, etc.

#### 2. Chromium Manager (`managers/chromium_manager.py`)
- Launches Chromium browser in full-screen kiosk mode
- Uses Xvfb (`:99`) for headless X11 virtual display
- Auto-detects display resolution from DRM
- Proper process cleanup (SIGTERM → SIGKILL escalation)

**Dependencies**:
```bash
sudo apt-get install xvfb chromium-browser
.venv/bin/pip install jinja2
```

#### 3. Now-Playing Web Interface
- **Template**: `templates/now-playing.html`
- **CSS**: `static/css/now-playing.css` (animations, blur effects)
- **JavaScript**: `static/js/now-playing.js` (WebSocket client)
- **Route**: `GET /now-playing` → renders Jinja2 template

**Features**:
- Blurred album art background
- Google Sans font
- Auto-scrolling for long track names
- Real-time updates via WebSocket
- Reconnection logic

### Display Mode Switching

The system supports multiple **mutually exclusive** display modes:

| Mode | Renderer | Manager | Notes |
|------|----------|---------|-------|
| YouTube Video | MPV (video pool) | PlaybackManager | Hardware-decoded |
| Audio Streams | MPV (audio pool) | AudioManager | PulseAudio/PipeWire |
| Static Background | MPV (video pool) | BackgroundManager | Default mode |
| **Spotify Now-Playing** | **Chromium kiosk** | **SpotifyManager** | Web-based ✨ |
| Image Display | MPV (video pool) | BackgroundManager | QR codes, etc. |

**Switching Logic**:
- Starting YouTube → stops Chromium (if running), uses MPV
- Starting Spotify → stops MPV, launches Chromium to `/now-playing`
- Stopping Spotify → stops Chromium, returns to static background

**Backward Compatibility**: All existing features (YouTube, audio, Chromecast) work unchanged. MPV pools remain initialized for instant switching.

### Web Mode Flow (Spotify Example)

1. **Spotify track changes** (librespot webhook → `/spotify/event`)
2. **SpotifyManager** broadcasts via WebSocket:
   ```json
   {
     "event": "track_changed",
     "data": {
       "name": "Track Name",
       "artists": "Artist Name",
       "album": "Album Name",
       "album_art_url": "https://...",
       "duration_ms": 240000
     }
   }
   ```
3. **SpotifyManager** calls `background_manager.start_now_playing_web_mode()`
4. **BackgroundManager** → **ChromiumManager** launches kiosk:
   ```bash
   Xvfb :99 -screen 0 1920x1080x24 &
   DISPLAY=:99 chromium-browser --kiosk http://localhost/now-playing
   ```
5. **Now-Playing Page** connects to WebSocket, receives updates
6. **Display updates** in real-time without regenerating images

### Fallback Mode

If Chromium fails to start (not installed, Xvfb error, etc.):
- System automatically falls back to legacy PIL/FFmpeg video mode
- Error logged but playback continues
- Check logs: `sudo journalctl -u hsg-canvas | grep Chromium`

### Testing Web Features

```bash
# Test WebSocket endpoint (requires wscat or similar)
wscat -c ws://localhost/ws/spotify-events

# Test now-playing page in browser
xdg-open http://localhost/now-playing

# Check active connections
curl http://localhost/ws/status

# Monitor Chromium processes
ps aux | grep chromium
ps aux | grep Xvfb
```

### Future Phases (Not Yet Implemented)

- **Phase 2**: Static background as web page (clock, QR codes, widgets)
- **Phase 3**: Audio visualizations, system dashboards, screensavers

### Troubleshooting

**Chromium not starting**:
```bash
# Check if installed
which chromium-browser xvfb

# Install if missing
sudo apt-get install xvfb chromium-browser

# Check logs
sudo journalctl -u hsg-canvas | grep -i chromium
```

**WebSocket not connecting**:
```bash
# Check endpoint
curl http://localhost/ws/status

# Test from browser console
const ws = new WebSocket('ws://localhost/ws/spotify-events');
ws.onmessage = (e) => console.log(e.data);
```

**Display not showing**:
- Xvfb renders to virtual display `:99` (not physical output)
- For actual HDMI output, may need display routing (see `WEB_DISPLAY_IMPLEMENTATION.md`)

## Dependencies

### System Packages

```bash
# Core media playback
sudo apt-get install mpv ffmpeg

# Web-based display (Phase 1)
sudo apt-get install xvfb chromium-browser

# Optional: CEC control
sudo apt-get install cec-utils
```

### Python Packages (venv)

All Python dependencies are in `requirements.txt` and installed in `.venv/`:

```bash
# Install/update dependencies
.venv/bin/pip install -r requirements.txt --break-system-packages

# Key packages:
# - fastapi==0.128.4 (upgraded Feb 2026 for lifespan support)
# - uvicorn==0.40.0
# - jinja2==3.1.6 (for template rendering)
# - pychromecast==13.1.0
# - yt-dlp==2025.09.26
# - Pillow==10.1.0
# - playwright==1.40.0 (webcast feature)
```

**Note**: Raspberry Pi requires `--break-system-packages` flag for pip installs
