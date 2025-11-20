# Output Target Management System

HSG Canvas now has a unified output target management system that allows seamless switching between local (HDMI/Audio Hat) and remote (Chromecast) playback targets.

## Architecture

### Components

1. **OutputTargetManager** (`managers/output_target_manager.py`)
   - Central manager for all output targets
   - Auto-discovers Chromecast devices
   - Routes playback to appropriate target
   - Keeps Chromecast code isolated from core functionality

2. **Target Types**
   - `local-video`: HDMI Display (default for video)
   - `local-audio`: Audio Hat (default for audio)
   - `chromecast-{uuid}`: Chromecast devices (auto-discovered)

3. **API Routes** (`routes.py`)
   - `/targets` - List all available targets
   - `/targets/refresh` - Manually refresh Chromecast discovery
   - `/targets/status` - Get current target status
   - `/targets/play/video` - Play video on specific target
   - `/targets/play/audio` - Play audio on specific target
   - `/targets/stop` - Stop playback on active targets

## Usage

### List Available Targets

```bash
curl http://localhost/targets
```

Response:
```json
{
  "targets": [
    {
      "id": "local-video",
      "type": "local-video",
      "name": "HDMI Display (Local)",
      "capabilities": ["video", "audio"],
      "is_available": true
    },
    {
      "id": "local-audio",
      "type": "local-audio",
      "name": "Audio Hat (Local)",
      "capabilities": ["audio"],
      "is_available": true
    },
    {
      "id": "chromecast-abc123",
      "type": "chromecast",
      "name": "Dining room TV (Chromecast)",
      "capabilities": ["video", "audio"],
      "is_available": true
    }
  ],
  "defaults": {
    "video": "local-video",
    "audio": "local-audio"
  },
  "active": {
    "video": null,
    "audio": null
  }
}
```

### Play Video on Specific Target

```bash
# Play on default (HDMI)
curl -X POST http://localhost/targets/play/video \
  -H "Content-Type: application/json" \
  -d '{"youtube_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}'

# Play on Chromecast
curl -X POST "http://localhost/targets/play/video?target=chromecast-abc123" \
  -H "Content-Type: application/json" \
  -d '{"youtube_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}'
```

### Play Audio on Specific Target

```bash
# Play on default (Audio Hat)
curl -X POST http://localhost/targets/play/audio \
  -H "Content-Type: application/json" \
  -d '{"stream_url": "https://ice1.somafm.com/groovesalad-128-mp3", "volume": 75}'

# Play on Chromecast
curl -X POST "http://localhost/targets/play/audio?target=chromecast-abc123" \
  -H "Content-Type: application/json" \
  -d '{"stream_url": "https://ice1.somafm.com/groovesalad-128-mp3", "volume": 75}'
```

### Refresh Chromecast Discovery

```bash
curl -X POST http://localhost/targets/refresh
```

Response:
```json
{
  "message": "Discovered 2 Chromecast device(s)",
  "chromecasts_found": 2,
  "total_targets": 4
}
```

### Stop Playback

```bash
# Stop all playback
curl -X POST http://localhost/targets/stop

# Stop only video
curl -X POST "http://localhost/targets/stop?media_type=video"

# Stop only audio
curl -X POST "http://localhost/targets/stop?media_type=audio"
```

## Features

### Auto-Discovery
- Chromecasts are automatically discovered on startup
- Auto-discovery runs every 5 minutes to detect new devices
- Manual refresh available via `/targets/refresh` endpoint

### Default Targets
- Video defaults to HDMI Display
- Audio defaults to Audio Hat
- Can be changed programmatically if needed

### Seamless Integration
- Existing `/playback/youtube` and `/audio/start` endpoints still work (use defaults)
- New `/targets/play/*` endpoints allow explicit target selection
- Backward compatible with existing code

### Chromecast Isolation
- All Chromecast-specific code is in `ChromecastManager`
- OutputTargetManager acts as abstraction layer
- Easy to add new target types (e.g., AirPlay, DLNA) in the future

## Web Interface Integration

The web interface can be updated to:
1. Show available targets in a dropdown
2. Add "Refresh Chromecasts" button
3. Display active target for video/audio
4. Allow target selection before starting playback

Example implementation:
```javascript
// Fetch targets
const targets = await fetch('/targets').then(r => r.json());

// Populate target selector
const videoTargets = targets.targets.filter(t => t.capabilities.includes('video'));
const audioTargets = targets.targets.filter(t => t.capabilities.includes('audio'));

// Play on selected target
await fetch(`/targets/play/video?target=${selectedTargetId}`, {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({youtube_url: url})
});
```

## Architecture Benefits

1. **Separation of Concerns**
   - Core Canvas functionality unchanged
   - Chromecast code fully isolated
   - Easy to test each component

2. **Extensibility**
   - New target types can be added easily
   - No changes to existing managers needed
   - Future-proof design

3. **User Experience**
   - Seamless switching between outputs
   - Auto-discovery of new devices
   - Clear indication of active target

4. **Backward Compatibility**
   - All existing endpoints still work
   - No breaking changes
   - Progressive enhancement

## Implementation Files

- `managers/output_target_manager.py` - Core target management
- `routes.py` - API endpoints (lines 1335-1486)
- `main.py` - Integration and initialization
- `managers/chromecast_manager.py` - Chromecast-specific code (isolated)

## Future Enhancements

- Web interface with target selector dropdowns
- Remember user's preferred target per media type
- Support for AirPlay targets
- Support for DLNA/UPnP targets
- Multi-target playback (same media on multiple outputs)
- Target health monitoring
- Automatic failover to default if target becomes unavailable
