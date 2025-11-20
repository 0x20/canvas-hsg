# Audio & Video Playback Fixes

This document describes the critical fixes applied to HSG Canvas to enable audio streaming, Spotify Connect, and YouTube playback.

## Issues Fixed

### 1. Audio Streams Not Playing
**Problem**: MPV processes could not access PulseAudio/PipeWire when started by systemd service.

**Root Cause**: Missing `XDG_RUNTIME_DIR` environment variable in systemd service prevented MPV from connecting to the user's audio server at `/run/user/1000/pulse/native`.

**Fix**: Added to `hsg-canvas.service`:
```ini
Environment=XDG_RUNTIME_DIR=/run/user/1000
```

### 2. MPV Idle Mode Not Auto-Playing
**Problem**: After loading a file with `loadfile` command, MPV remained paused in idle mode.

**Root Cause**: MPV with `--idle=yes` flag doesn't automatically start playback after loading a file.

**Fixes Applied**:
- `managers/audio_manager.py:118` - Added explicit unpause after loading audio streams
- `managers/playback_manager.py:110` - Added explicit unpause after loading YouTube videos

**Code Added**:
```python
# CRITICAL: Explicitly unpause to start playback in idle mode
# MPV in idle mode doesn't auto-play after loadfile - we must explicitly unpause
await controller.send_command(["set_property", "pause", False])
```

### 3. YouTube Playback Failures
**Problem**: YouTube videos failing to load due to anti-bot measures.

**Root Cause**: Outdated yt-dlp version (2025.9.26) couldn't handle YouTube's JavaScript challenges.

**Fix**: Upgraded yt-dlp to latest version (2025.11.12) which includes:
- Support for YouTube's anti-bot challenges
- Node.js integration for JavaScript execution
- Latest extraction fixes

**Installation Script Update**: `setup.sh` now explicitly upgrades yt-dlp:
```bash
pip install --upgrade yt-dlp
```

## Installation Scripts Updated

### Files Modified:
1. **hsg-canvas.service** - Added `XDG_RUNTIME_DIR` environment variable
2. **setup.sh** - Added yt-dlp upgrade step during installation
3. **managers/audio_manager.py** - Added unpause command for audio playback
4. **managers/playback_manager.py** - Added unpause command for video playback

### What Works Now:
✅ Audio streaming (SomaFM, radio streams, direct URLs)  
✅ Spotify Connect via Raspotify ("HSG Canvas" device)  
✅ YouTube video playback with DRM hardware acceleration  
✅ Volume control  
✅ Metadata display for supported streams  

## Testing Verification

### Audio Stream Test:
```bash
curl -X POST http://localhost/audio/start \
  -H "Content-Type: application/json" \
  -d '{"stream_url": "https://ice1.somafm.com/groovesalad-128-mp3", "volume": 75}'
```

### YouTube Playback Test:
```bash
curl -X POST http://localhost/playback/youtube \
  -H "Content-Type: application/json" \
  -d '{"youtube_url": "https://www.youtube.com/watch?v=jNQXAC9IVRw", "duration": 30}'
```

### Spotify Connect:
1. Open Spotify app on phone (Premium account required)
2. Start playing music
3. Tap "Devices Available" icon
4. Select "HSG Canvas"

## Technical Details

### Audio Architecture:
- **PipeWire/PulseAudio**: User-space audio server running at `/run/user/1000/pulse/native`
- **MPV Pools**: Pre-spawned MPV processes with IPC control
- **Audio Device**: `pulse` (PipeWire compatibility layer)
- **Raspotify Backend**: `pulseaudio` with 320kbps bitrate

### Environment Variables Required:
```bash
DISPLAY=:0                        # X11 display for video
HOME=/home/hsg                    # User home directory
XDG_RUNTIME_DIR=/run/user/1000   # PulseAudio/PipeWire socket location
AUDIO_DEVICE=pulse                # MPV audio output device
```

## Future Maintenance

### Updating yt-dlp:
```bash
source .venv/bin/activate
pip install --upgrade yt-dlp
sudo systemctl restart hsg-canvas
```

### Checking Audio Status:
```bash
# Check PulseAudio sinks
pactl list sinks short

# Check active audio streams
pactl list sink-inputs

# Check MPV processes
ps aux | grep "mpv.*pool"

# Test audio device directly
mpv --audio-device=pulse <audio-url> --length=5
```

### Logs:
```bash
# HSG Canvas logs
sudo journalctl -u hsg-canvas -f

# Raspotify logs
sudo journalctl -u raspotify -f

# Filter for audio/playback issues
sudo journalctl -u hsg-canvas | grep -i "audio\|youtube\|error"
```

## Credits

Fixes applied: 2025-11-14
- XDG_RUNTIME_DIR systemd fix
- MPV idle mode unpause fix
- yt-dlp upgrade to latest
