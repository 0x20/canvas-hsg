#!/bin/bash
#
# HSG Canvas Startup Script with React Hot Reload
# - Starts Vite dev server on port 5173 (React now-playing display)
# - Starts FastAPI server on port 80
#

set -e

echo "=== HSG Canvas with React Hot Reload ==="
echo ""

# Clean up orphaned mpv processes from previous runs
echo "Cleaning up orphaned mpv processes..."
pkill -9 -f "mpv.*-mpv-pool" 2>/dev/null || true

# Clean up stale IPC sockets
rm -f /tmp/audio-mpv-pool-* /tmp/video-mpv-pool-* 2>/dev/null || true

# Clean up stale display processes from previous crashes
echo "Cleaning up stale display processes..."
killall -9 cage labwc 2>/dev/null || true
killall -9 chromium-browser 2>/dev/null || true
sudo killall -9 Xorg 2>/dev/null || true
sudo rm -f /tmp/.X1-lock /tmp/.X11-unix/X1 2>/dev/null || true

# Free port 80 and wait until it's actually released
sudo fuser -k 80/tcp 2>/dev/null || true
for i in $(seq 1 10); do
    if ! sudo fuser 80/tcp >/dev/null 2>&1; then
        break
    fi
    echo "Waiting for port 80 to be released... ($i)"
    sleep 1
done

# Brief pause to ensure cleanup completes
sleep 1

# Start Vite dev server in background
echo "Starting Vite dev server on port 5173..."
cd /home/hsg/srs_server/frontend
nohup npm run dev > /tmp/vite.log 2>&1 &
VITE_PID=$!
echo "Vite dev server started (PID: $VITE_PID)"
echo ""

# Wait for Vite to be ready
sleep 3

# Go back to project root
cd /home/hsg/srs_server

# Set audio device to use PulseAudio/PipeWire (avoids conflicts with Raspotify)
export AUDIO_DEVICE="pulse"
echo "Audio device: $AUDIO_DEVICE"

# Add deno to PATH for yt-dlp JavaScript runtime (helps with YouTube extraction)
export PATH="/home/hsg/.deno/bin:$PATH"

echo ""
echo "Starting FastAPI server on port 80..."

# Start the application
# Note: When run via systemd, we're already the correct user, so no sudo needed
if [ -n "$INVOCATION_ID" ]; then
    # Running under systemd
    exec .venv/bin/python main.py --production
else
    # Running manually, use sudo
    sudo -E .venv/bin/python main.py --production
fi

# Cleanup: kill Vite dev server when FastAPI exits
echo ""
echo "Shutting down Vite dev server..."
kill $VITE_PID 2>/dev/null || true
echo "Shutdown complete"
