#!/bin/bash

# Clean up orphaned mpv processes from previous runs
echo "Cleaning up orphaned mpv processes..."
pkill -9 -f "mpv.*-mpv-pool" 2>/dev/null || true

# Clean up stale IPC sockets
rm -f /tmp/audio-mpv-pool-* /tmp/video-mpv-pool-* 2>/dev/null || true

# Brief pause to ensure cleanup completes
sleep 0.5

# Set audio device to use PulseAudio/PipeWire (avoids conflicts with Raspotify)
export AUDIO_DEVICE="pulse"

# Start the application
# Note: When run via systemd, we're already the correct user, so no sudo needed
if [ -n "$INVOCATION_ID" ]; then
    # Running under systemd
    exec .venv/bin/python main.py --production
else
    # Running manually, use sudo
    sudo -E .venv/bin/python main.py --production
fi
