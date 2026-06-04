#!/bin/bash
#
# HSG Canvas Startup Script
# - Builds the React canvas (production bundle, served by FastAPI)
# - Starts FastAPI server on port 8000
# - Angie reverse proxy on port 80 handles external routing
#

set -e

# Resolve the repo root from this script's location so the service works
# regardless of install user or path (no hardcoded /home/hsg/srs_server).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== HSG Canvas ==="
echo ""

# Clean up stale display processes from previous crashes
echo "Cleaning up stale display processes..."
killall -9 cage labwc 2>/dev/null || true
killall -9 chromium-browser chromium 2>/dev/null || true
sudo killall -9 Xorg 2>/dev/null || true
sudo rm -f /tmp/.X1-lock /tmp/.X11-unix/X1 2>/dev/null || true
# Clear the kiosk's Chromium profile so a rebuilt bundle always loads fresh
# (the profile lives in /tmp and survives a service restart, otherwise caching
# a stale index.html that references old asset hashes).
rm -rf /tmp/chromium-hsg-canvas 2>/dev/null || true

# Brief pause to ensure cleanup completes
sleep 1

# Build the React canvas if dist is missing or older than any source file
cd "$SCRIPT_DIR/frontend"
NEED_BUILD=0
if [ ! -f dist/index.html ]; then
    NEED_BUILD=1
elif [ -n "$(find src public package.json vite.config.js -newer dist/index.html 2>/dev/null | head -1)" ]; then
    NEED_BUILD=1
fi
if [ "$NEED_BUILD" = "1" ]; then
    echo "Building React canvas..."
    [ -d node_modules ] || npm ci
    npm run build
    echo "Canvas built."
else
    echo "Canvas build is up to date."
fi
echo ""

# Go back to project root
cd "$SCRIPT_DIR"

# Set audio device to use PulseAudio/PipeWire (avoids conflicts with Raspotify)
export AUDIO_DEVICE="pulse"
echo "Audio device: $AUDIO_DEVICE"

# Add venv bin and deno to PATH
export PATH="$SCRIPT_DIR/.venv/bin:$HOME/.deno/bin:$PATH"

echo ""
echo "Starting FastAPI server on port 8000..."

# Start the application (Angie handles port 80, FastAPI listens on 8000)
exec .venv/bin/python main.py --production
