#!/bin/bash

# Clean up orphaned mpv processes from previous runs
echo "Cleaning up orphaned mpv processes..."
pkill -9 -f "mpv.*-mpv-pool" 2>/dev/null || true

# Clean up stale IPC sockets
rm -f /tmp/audio-mpv-pool-* /tmp/video-mpv-pool-* 2>/dev/null || true

# Brief pause to ensure cleanup completes
sleep 0.5

# Set audio device to use DAC on card 3 by default
export AUDIO_DEVICE="alsa/sysdefault:CARD=3"

# Start the application
sudo -E .venv/bin/python main.py --production
