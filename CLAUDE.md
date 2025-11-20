# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is HSG Canvas (Hackerspace.gent Canvas) - a FastAPI-based web application that manages media streaming and playback on Raspberry Pi devices. The system can republish media streams to an SRS (Simple Realtime Server) RTMP server and control local media playback using various video players.
There is an SRS running alongside our python app, the idea is that our app is running with the SRS on a raspberry pi, and is used to put things on a display. Streams via SRS, images and youtube via other means.

## Architecture

### Core Components

- **Main Application** (`main.py`): Entry point and FastAPI application setup with lifespan management
- **MPV Pools** (`core/mpv_pools.py`): Audio and video MPV process pool management with IPC
- **Managers** (`managers/`): Specialized managers for audio, playback, streams, display, etc.
- **API Routes** (`api/`): RESTful API endpoints organized by functionality
- **Web Interface** (`index.html`): Full-featured control panel for stream management
- **Static Assets** (`static/` directory): CSS/JS resources for the web interface

### Key Features

- **Stream Republishing**: Accepts various input sources (files, RTSP cameras, HTTP streams) and republishes to SRS RTMP server
- **Multi-Player Support**: Supports mpv, ffplay, omxplayer, and VLC with optimized configurations for Raspberry Pi
- **YouTube Integration**: Direct YouTube video playback with duration controls
- **Chromecast Support**: Cast audio and video to Chromecast devices on the network with automatic playback management
- **Spotify Connect**: Cast Spotify Premium audio from phone to Pi speakers via Raspotify
- **Background Management**: Customizable background images with auto-generation
- **System Monitoring**: Real-time system stats (CPU, memory, temperature) and stream diagnostics

### External Dependencies

- **SRS Server**: Expected to run on `pixelflut:1935` (RTMP) and `pixelflut:8080` (HTTP-FLV/HLS)
- **FFmpeg**: Used for stream processing and republishing
- **Media Players**: mpv (recommended), ffplay, omxplayer, or VLC for local playback
- **PyChromecast**: Python library for discovering and controlling Chromecast devices (sender)
- **netifaces**: Python library for network interface detection (receiver)
- **Raspotify**: Spotify Connect client service for casting from Premium accounts
- **PIL/Pillow**: For background image generation and processing

## Development Commands

### Installation & Setup
```bash
# Install Python dependencies
pip3 install -r requirements.txt

# Run the server
python3 main.py

# Or use the start script (includes AUDIO_DEVICE setup)
./start.sh
```

### Server Operation
```bash
# Start server (defaults to 0.0.0.0:8000)
python3 main.py

# Alternative with uvicorn directly
uvicorn main:app --host 0.0.0.0 --port 8000

# With systemd
sudo systemctl start hsg-canvas
sudo systemctl enable hsg-canvas  # Auto-start on boot
```

### Key API Endpoints
- `GET /` - Web interface
- `POST /streams/{key}/start` - Start stream republishing
- `POST /playback/{key}/start` - Start local playback
- `POST /playback/youtube` - Play YouTube videos
- `POST /audio/start` - Start audio streaming
- `GET /audio/spotify/status` - Check Spotify Connect service status
- `GET /chromecast/discover` - Discover Chromecast devices on network
- `POST /chromecast/start` - Cast media to Chromecast device (sender)
- `POST /chromecast/stop` - Stop current Chromecast session (sender)
- `GET /chromecast/status` - Get Chromecast casting status (sender)
- `POST /cast-receiver/receive` - Receive cast from phone/tablet
- `GET /cast-receiver/status` - Get cast receiver status
- `GET /dd.xml` - DIAL device description for discovery
- `GET /diagnostics` - System diagnostics for troubleshooting
- `GET /status` - System and streaming status

## Configuration

### SRS Server Configuration
```python
SRS_RTMP_URL = "rtmp://pixelflut:1935/live"
SRS_HTTP_FLV_URL = "http://pixelflut:8080/live" 
SRS_HLS_URL = "http://pixelflut:8080/live"
SRS_API_URL = "http://pixelflut:1985/api/v1"
```

### MPV Configuration
The system uses dedicated MPV process pools with IPC control:
- **Audio Pool** (`core/mpv_pools.py:AudioMPVPool`): For audio-only streaming
- **Video Pool** (`core/mpv_pools.py:VideoMPVPool`): For video playback with DRM/KMS and hardware decoding

### Display Setup
The application supports multiple display methods:
- **X11**: Primary method using DISPLAY=:0
- **DRM**: Direct rendering for headless setups
- **Multiple image viewers**: feh, eog, gpicview as fallbacks

### Spotify Connect Setup
The system includes Raspotify for Spotify Premium casting:

**Installation:**
```bash
# Raspotify is already installed via official script
curl -sL https://dtcooper.github.io/raspotify/install.sh | sudo sh
```

**Configuration:** (`/etc/raspotify/conf`)
- **Device Name**: "HSG Canvas"
- **Audio Device**: `sysdefault:CARD=3` (matches AUDIO_DEVICE)
- **Bitrate**: 320kbps for maximum quality
- **Initial Volume**: 70%
- **Features**: Volume normalization enabled, gapless playback

**Usage:**
1. Ensure Raspotify service is running: `sudo systemctl status raspotify`
2. Open Spotify app on phone (Premium account required)
3. Start playing music
4. Tap "Devices Available" button (speaker icon)
5. Select "HSG Canvas" from device list
6. Audio plays through Pi speakers

**Service Management:**
```bash
# Check status
sudo systemctl status raspotify

# Restart service
sudo systemctl restart raspotify

# View logs
sudo journalctl -u raspotify -f
```

**Audio Device Sharing:**
- Raspotify shares `AUDIO_DEVICE` (CARD=3) with HSG Canvas audio streams
- Only one audio source can play at a time
- Raspotify runs independently as a systemd service

### Chromecast Setup (Sender & Receiver)
The system includes both Chromecast sender and receiver functionality:

#### Casting TO Other Devices (Sender)
PyChromecast library for casting media to Chromecast devices on the network:

**Features:**
- Automatic device discovery on local network via subprocess isolation (zero FD leaks)
- Cast audio and video URLs to any Chromecast device
- Automatic media type detection (audio vs video)
- Smart playback management: stops local playback when casting starts
  - Video casting: stops both audio and video playback
  - Audio casting: stops only video playback (audio continues on Pi)
- Volume control and playback management (play/pause/stop)
- 24-hour discovery cache to minimize network overhead

**Usage:**
1. Ensure Chromecast device is on the same network as the Raspberry Pi
2. Use the web interface to discover devices
3. Enter a media URL (direct MP3/MP4 URL or streaming URL)
4. Select a Chromecast device (or use the first available)
5. Click "START CAST" to begin casting

**Supported Media:**
- Audio formats: MP3, M4A, AAC, OGG, FLAC, WAV
- Video formats: MP4, WebM, MKV, AVI, MOV
- Streaming URLs: Radio streams, video streams

**API Examples:**
```bash
# Discover Chromecast devices
curl http://localhost:8000/chromecast/discover

# Cast media to Chromecast
curl -X POST http://localhost:8000/chromecast/start \
  -H "Content-Type: application/json" \
  -d '{"media_url": "http://example.com/song.mp3", "device_name": "Living Room TV"}'

# Check casting status
curl http://localhost:8000/chromecast/status

# Stop casting
curl -X POST http://localhost:8000/chromecast/stop
```

**Technical Notes:**
- Media URLs must be publicly accessible (Chromecast fetches directly from URL)
- Local file playback is automatically stopped when casting begins
- Casting quality depends on network bandwidth and Chromecast model
- **File Descriptor Leak Fix**: Discovery runs in isolated subprocess to prevent FD leaks from pychromecast/zeroconf
  - Previous approach leaked ~5 FDs per discovery cycle
  - Subprocess approach achieves zero leaks by isolating zeroconf multicast sockets
  - Device info is cached for 24 hours, minimizing subprocess spawning overhead

#### Receiving Casts FROM Phones/Tablets (Receiver)
DIAL/SSDP server for appearing as a cast target in casting apps:

**Features:**
- Auto-starts on server launch (port 1900 for SSDP multicast)
- Makes Canvas discoverable as "HSG Canvas" in cast menus
- Receives YouTube URLs, audio streams, and video URLs from phones
- Automatic media type detection and playback routing
- Session management with playback status tracking

**How It Works:**
1. Canvas runs an SSDP responder listening for M-SEARCH requests
2. Responds with DIAL device description XML at `/dd.xml`
3. When a cast is initiated, media URL is sent to `/cast-receiver/receive`
4. Canvas automatically plays the media using appropriate manager (YouTube → PlaybackManager, Audio → AudioManager)

**Usage from Phone/Tablet:**
1. Open a cast-enabled app (YouTube, Chrome, streaming apps)
2. Tap the cast icon
3. Look for "HSG Canvas" in available devices
4. Select it to cast media directly to the Canvas display/speakers

**API Endpoints:**
```bash
# Get receiver status
curl http://localhost:8000/cast-receiver/status

# Manually send a cast (simulates phone casting)
curl -X POST http://localhost:8000/cast-receiver/receive \
  -H "Content-Type: application/json" \
  -d '{"media_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "title": "Test Video"}'

# Stop current cast session
curl -X POST http://localhost:8000/cast-receiver/stop-session
```

**Technical Details:**
- Uses SSDP multicast (239.255.255.250:1900) for device discovery
- DIAL protocol for app launching/control
- Receiver runs automatically on server startup
- Compatible with standard Chromecast sender apps (YouTube, Chrome, etc.)

**Supported Content:**
- YouTube videos (direct integration with PlaybackManager)
- Direct audio URLs (MP3, M4A, streaming radio)
- Direct video URLs (MP4, WebM - limited support)

## Development Notes

### Stream Processing
- Uses FFmpeg with optimized H.264 encoding settings for RTMP output
- Supports various input formats: local files, RTSP streams, HTTP streams
- Process management uses `os.setsid()` for proper cleanup

### Error Handling
- Comprehensive fallback mechanisms for display methods
- Graceful process termination with timeout handling
- Detailed logging for troubleshooting streaming issues

### Raspberry Pi Optimizations
- Temperature monitoring via `/sys/class/thermal/thermal_zone0/temp`
- GPU memory detection with `vcgencmd`
- Hardware-specific player configurations (omxplayer for legacy Pi support)

### File Structure
```
/home/hsg/srs_server/
├── main.py                      # Entry point - FastAPI application
├── config.py                    # Configuration constants
├── background_modes.py          # Background manager
├── webcast_manager.py           # Webcast functionality
├── start.sh                     # Startup script
│
├── core/                        # MPV management
│   ├── mpv_controller.py       # IPC controller for single mpv process
│   ├── mpv_pools.py            # Audio/Video MPV pools
│   └── health_monitor.py       # Auto-recovery for pools
│
├── managers/                    # Business logic
│   ├── audio_manager.py        # Audio streaming
│   ├── playback_manager.py     # Video/YouTube playback
│   ├── image_manager.py        # Image/QR display
│   ├── stream_manager.py       # Stream republishing
│   ├── screen_stream_manager.py # Screen capture
│   ├── chromecast_manager.py   # Chromecast casting (sender)
│   ├── cast_receiver_manager.py # Cast receiver (receive from phones)
│   ├── display_detector.py     # Display detection
│   ├── framebuffer_manager.py  # Framebuffer control
│   └── hdmi_cec.py            # HDMI-CEC control
│
├── routes.py                    # Unified API routes
│   │                            # - Audio endpoints
│   │                            # - Playback endpoints
│   │                            # - Stream endpoints
│   │                            # - Screen endpoints
│   │                            # - Display endpoints
│   │                            # - Background endpoints
│   │                            # - CEC endpoints
│   │                            # - System endpoints
│   │                            # - Webcast endpoints
│   │                            # - Chromecast endpoints (sender)
│   │                            # - Cast Receiver endpoints (receiver)
│
├── models/                      # Request/response models
│   └── request_models.py       # Pydantic models for API validation
│
├── index.html                   # Web interface
├── requirements.txt             # Python dependencies
├── static/                      # Static assets (CSS/JS)
└── /tmp/stream_images/          # Runtime image storage
```

## Testing & Diagnostics

### Diagnostic Endpoints
- **`/diagnostics`** - System capabilities and configuration:
  - Display methods (X11, DRM availability)
  - Available image viewers and media players
  - DRM device access permissions
  - CPU info and GPU memory allocation
  - Current process status
- **`/status`** - Real-time system and streaming status:
  - System stats (CPU %, memory %, temperature, disk usage)
  - Active stream count and current playback info
  - SRS server connection status
- **`/health`** - Simple health check with timestamp
- **`/docs/quick-start`** - API usage examples and player recommendations

### Common Diagnostic Scenarios
- **Display Issues**: Check `/diagnostics` for X11/DRM availability and viewer compatibility
- **Performance**: Monitor `/status` for CPU/memory usage and temperature throttling
- **Streaming Problems**: Verify SRS server connectivity and active stream status
- **Player Selection**: Use diagnostics to identify optimal player for current Pi configuration

### Quick Diagnostic Commands
```bash
# Check system capabilities
curl localhost:8000/diagnostics | python3 -m json.tool

# Monitor system performance  
curl localhost:8000/status | python3 -m json.tool

# Verify server health
curl localhost:8000/health
```
