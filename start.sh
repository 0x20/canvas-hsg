#!/bin/bash
#
# HSG Canvas Startup Script with React Hot Reload
# - Starts Vite dev server on port 5173 (React now-playing display)
# - Starts FastAPI server on port 8000
# - Angie reverse proxy on port 80 handles external routing
#

set -e

echo "=== HSG Canvas with React Hot Reload ==="
echo ""

# Clean up stale display processes from previous crashes
echo "Cleaning up stale display processes..."
killall -9 cage labwc 2>/dev/null || true
killall -9 chromium-browser 2>/dev/null || true
sudo killall -9 Xorg 2>/dev/null || true
sudo rm -f /tmp/.X1-lock /tmp/.X11-unix/X1 2>/dev/null || true

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

# Add venv bin and deno to PATH
export PATH="/home/hsg/srs_server/.venv/bin:/home/hsg/.deno/bin:$PATH"

echo ""
echo "Starting FastAPI server on port 8000..."

# Start the application (Angie handles port 80, FastAPI listens on 8000)
exec .venv/bin/python main.py --production

# Cleanup: kill Vite dev server when FastAPI exits
echo ""
echo "Shutting down Vite dev server..."
kill $VITE_PID 2>/dev/null || true
echo "Shutdown complete"
