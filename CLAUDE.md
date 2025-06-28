# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is HSG Canvas (Hackerspace.gent Canvas) - a FastAPI-based web application that manages media streaming and playback on Raspberry Pi devices. The system can republish media streams to an SRS (Simple Realtime Server) RTMP server and control local media playback using various video players.
There is an SRS running alongside our python app, the idea is that our app is running with the SRS on a raspberry pi, and is used to put things on a display. Streams via SRS, images and youtube via other means.

## Architecture

### Core Components

- **StreamManager Class** (`srsserver.py:76-570`): Central orchestrator managing streaming processes, media playback, and background display
- **FastAPI Web Server** (`srsserver.py:571-869`): REST API and web interface serving endpoints
- **Web Interface** (`index.html`): Full-featured control panel for stream management
- **Static Assets** (`static/` directory): CSS/JS resources for the web interface

### Key Features

- **Stream Republishing**: Accepts various input sources (files, RTSP cameras, HTTP streams) and republishes to SRS RTMP server
- **Multi-Player Support**: Supports mpv, ffplay, omxplayer, and VLC with optimized configurations for Raspberry Pi
- **YouTube Integration**: Direct YouTube video playback with duration controls
- **Background Management**: Customizable background images with auto-generation
- **System Monitoring**: Real-time system stats (CPU, memory, temperature) and stream diagnostics

### External Dependencies

- **SRS Server**: Expected to run on `pixelflut:1935` (RTMP) and `pixelflut:8080` (HTTP-FLV/HLS)
- **FFmpeg**: Used for stream processing and republishing
- **Media Players**: mpv (recommended), ffplay, omxplayer, or VLC for local playback
- **PIL/Pillow**: For background image generation and processing

## Development Commands

### Installation & Setup
```bash
# Install Python dependencies
pip3 install -r requirements.txt

# Run the server
python3 srsserver.py
```

### Server Operation
```bash
# Start server (defaults to 0.0.0.0:8000)
python3 srsserver.py

# Alternative with uvicorn directly
uvicorn srsserver:app --host 0.0.0.0 --port 8000
```

### Key API Endpoints
- `GET /` - Web interface
- `POST /streams/{key}/start` - Start stream republishing  
- `POST /playback/{key}/start` - Start local playback
- `POST /playback/youtube` - Play YouTube videos
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

### Player Commands
The system includes optimized configurations for each supported player in `PLAYER_COMMANDS` dict (`srsserver.py:34-56`). The "optimized" mode is recommended for Raspberry Pi performance.

### Display Setup
The application supports multiple display methods:
- **X11**: Primary method using DISPLAY=:0
- **DRM**: Direct rendering for headless setups
- **Multiple image viewers**: feh, eog, gpicview as fallbacks

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
├── srsserver.py          # Main FastAPI application
├── index.html           # Web interface
├── requirements.txt     # Python dependencies
├── static/             # Static assets (CSS/JS)
└── /tmp/stream_images/ # Runtime image storage
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
