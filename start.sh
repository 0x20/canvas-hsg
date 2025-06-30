#!/bin/bash

# Stream Controller Startup Script for Headless Pi4
# This script ensures proper permissions and starts the server optimally

echo "🚀 Starting DRM-Accelerated Stream Controller"
echo "============================================="

# Check if running as root
if [[ $EUID -eq 0 ]]; then
    echo "⚠️  Running as root - this will work but not recommended for production"
    START_AS_ROOT=true
else
    echo "👤 Running as user: $USER"
    START_AS_ROOT=false
fi

# Check DRM device permissions
echo ""
echo "🔍 Checking DRM permissions..."
if [ -d "/dev/dri" ]; then
    for device in /dev/dri/*; do
        if [ -c "$device" ]; then
            device_name=$(basename "$device")
            if [ -r "$device" ] && [ -w "$device" ]; then
                echo "✅ $device_name: accessible"
                DRM_ACCESSIBLE=true
            else
                echo "❌ $device_name: permission denied"
                DRM_ACCESSIBLE=false
            fi
        fi
    done
else
    echo "❌ /dev/dri not found - DRM not available"
    exit 1
fi

# Check if server file exists
if [ ! -f "srsserver.py" ]; then
    echo "❌ srsserver.py not found in current directory"
    echo "   Please run this script from the directory containing srsserver.py"
    exit 1
fi

# Function to start server
start_server() {
    local method="$1"
    echo ""
    echo "🎬 Starting server with: $method"
    echo "   Server will be available at: http://$(hostname -I | awk '{print $1}'):8000"
    echo "   Press Ctrl+C to stop"
    echo ""
    
    case $method in
        "sudo")
            sudo python3 srsserver.py
            ;;
        "user")
            python3 srsserver.py
            ;;
        "screen")
            echo "Starting in screen session 'stream-controller'..."
            screen -dmS stream-controller sudo python3 srsserver.py
            echo "✅ Server started in background"
            echo "   To attach: screen -r stream-controller" 
            echo "   To detach: Ctrl+A then D"
            echo "   To stop: screen -S stream-controller -X quit"
            ;;
    esac
}

# Check if we can use screen for background operation
if command -v screen >/dev/null 2>&1; then
    SCREEN_AVAILABLE=true
else
    SCREEN_AVAILABLE=false
fi

# Determine best startup method
echo ""
echo "🎯 Startup Options:"
echo "1. Run with sudo (recommended for headless - fixes DRM permissions)"
echo "2. Run as current user (only if DRM permissions are fixed)"
if [ "$SCREEN_AVAILABLE" = true ]; then
    echo "3. Run in background screen session with sudo"
fi
echo "4. Show diagnostics first"
echo "5. Exit"

echo ""
read -p "Select option (1-5): " choice

case $choice in
    1)
        start_server "sudo"
        ;;
    2)
        if [ "$DRM_ACCESSIBLE" = false ]; then
            echo "⚠️  Warning: DRM permissions not available as current user"
            echo "   This may cause playback failures"
            read -p "Continue anyway? (y/N): " confirm
            if [[ $confirm =~ ^[Yy]$ ]]; then
                start_server "user"
            else
                echo "Cancelled"
                exit 0
            fi
        else
            start_server "user"
        fi
        ;;
    3)
        if [ "$SCREEN_AVAILABLE" = true ]; then
            start_server "screen"
        else
            echo "❌ Screen not available"
            exit 1
        fi
        ;;
    4)
        echo ""
        echo "📊 System Diagnostics"
        echo "===================="
        echo "User: $USER"
        echo "Groups: $(groups)"
        echo "DRM devices:"
        ls -la /dev/dri/ 2>/dev/null || echo "  No DRM devices found"
        echo ""
        echo "GPU Memory: $(vcgencmd get_mem gpu 2>/dev/null || echo 'Unknown')"
        echo "ARM Memory: $(vcgencmd get_mem arm 2>/dev/null || echo 'Unknown')"
        echo ""
        echo "Python version: $(python3 --version)"
        echo "MPV available: $(which mpv >/dev/null 2>&1 && echo 'Yes' || echo 'No')"
        echo ""
        echo "Boot config (GPU related):"
        grep -E "(gpu_mem|dtoverlay.*vc4)" /boot/config.txt 2>/dev/null || echo "  No GPU config found"
        echo ""
        read -p "Press Enter to return to menu..."
        exec "$0"  # Restart script
        ;;
    5)
        echo "Goodbye!"
        exit 0
        ;;
    *)
        echo "Invalid option"
        exit 1
        ;;
esac

# If we get here, server has stopped
echo ""
echo "📋 Server stopped. Quick restart options:"
echo "  sudo python3 srsserver.py              # Direct restart with sudo"
echo "  ./start_server.sh                      # Restart with this script"
echo "  screen -dmS stream sudo python3 srsserver.py  # Background restart"