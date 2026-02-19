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

# Run server (production, port 8000 — Angie proxies port 80)
python3 main.py --production

# Run via start script (kills orphan mpv processes, sets AUDIO_DEVICE, runs production)
./start.sh

# One-time setup (installs Angie, systemd services, raspotify config)
sudo ./setup.sh

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
- **`config/`** - Deployment config files (Angie, systemd service, raspotify drop-in)
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

## Critical Gotchas

### setup.sh overwrites config files
`setup.sh` is a full system provisioning script. Running it **replaces** `/etc/raspotify/conf` and systemd service files. If you add config to those files outside of setup.sh, the next setup.sh run will erase it. **Always update setup.sh when changing deployment config.**

Key things setup.sh must preserve:
- `LIBRESPOT_ONEVENT=/home/hsg/srs_server/raspotify-onevent.sh` in `/etc/raspotify/conf` (without this, Spotify events don't reach FastAPI and the display never updates)
- Raspotify systemd drop-in at `config/raspotify/onevent.conf` (User=hsg, PrivateUsers=false, ProtectHome=false)

### Raspotify + PipeWire/PulseAudio
Raspotify's default systemd sandbox has `PrivateUsers=true` (remaps UIDs, breaking socket auth) and `ProtectHome=true` (blocks `/home/hsg`). Both must be overridden in the drop-in for PulseAudio to work. Symptom: `Audio Sink Error Connection Refused: <PulseAudioSink>`.

### Vite base path + Angie proxy
When proxying a Vite app under a subpath (`/spotify/`), you must:
1. Set `base: '/spotify/'` in `vite.config.js` (so asset URLs get the prefix)
2. Use `proxy_pass http://upstream;` (NO trailing slash) in Angie so the `/spotify/` prefix passes through to Vite
If you strip the prefix (`proxy_pass http://upstream/;` WITH trailing slash), Vite gets `/` but its assets reference `/spotify/...` paths → redirect loop.

### Angie apt repo URL format
The correct URL is `deb https://download.angie.software/angie/debian/12 bookworm main` (note the `/12` version number). The format without the version number returns 404.
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

### Reverse Proxy (Angie)

Angie reverse proxy on port 80 routes all external traffic:

| URL Path | Backend | Content |
|----------|---------|---------|
| `/` | FastAPI:8000 | Control panel |
| `/spotify/` | Vite:5173 | React display app (HMR works) |
| `/static/*` | FastAPI:8000 | Control panel assets |
| `/ws/*` | FastAPI:8000 | WebSocket endpoints |
| `/docs` | FastAPI:8000 | OpenAPI docs |
| All API routes | FastAPI:8000 | REST API |

Config files (all in repo, symlinked/copied by `setup.sh`):
- `config/angie/hsg-canvas.conf` → `/etc/angie/http.d/hsg-canvas.conf`
- `config/hsg-canvas.service` → `/etc/systemd/system/hsg-canvas.service`
- `config/raspotify/onevent.conf` → `/etc/systemd/system/raspotify.service.d/onevent.conf`

### Service Configuration

The service file is at `config/hsg-canvas.service` (copied to `/etc/systemd/system/` by setup.sh).

**Key Points**:
- Runs as user `hsg` (not root)
- Uses virtual environment via `start.sh`
- Auto-restarts on crash (10 second delay)
- No longer needs `CAP_NET_BIND_SERVICE` (Angie owns port 80, FastAPI listens on 8000)
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
Spotify Event (librespot onevent hook)
    ↓  POST /audio/spotify/event
SpotifyManager → broadcasts via WebSocket
    ↓
WebSocketManager → pushes to all clients
    ↓
React App at /spotify/ (via Angie → Vite:5173)
    ↓
Chromium Kiosk Mode (cage Wayland → http://127.0.0.1/spotify/)
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
