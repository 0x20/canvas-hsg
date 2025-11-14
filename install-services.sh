#!/bin/bash

# HSG Canvas Services Installation Script
# This script installs systemd services for:
# - SRS Server (Docker container)
# - HSG Canvas (Python app)
# - Raspotify (already installed, just verified)

set -e

echo "=== HSG Canvas Services Installation ==="
echo ""

# Check if running with sudo
if [ "$EUID" -ne 0 ]; then 
    echo "Please run with sudo: sudo ./install-services.sh"
    exit 1
fi

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# 1. Install SRS Server service
echo "[1/3] Installing SRS Server service..."
cp "$SCRIPT_DIR/srs-server.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable srs-server.service
echo "✓ SRS Server service installed and enabled"
echo ""

# 2. Install HSG Canvas service
echo "[2/3] Installing HSG Canvas service..."
cp "$SCRIPT_DIR/hsg-canvas.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable hsg-canvas.service
echo "✓ HSG Canvas service installed and enabled"
echo ""

# 3. Verify Raspotify service
echo "[3/3] Verifying Raspotify service..."
if systemctl is-enabled raspotify.service >/dev/null 2>&1; then
    echo "✓ Raspotify service is already installed and enabled"
else
    echo "⚠ Raspotify is not enabled, enabling now..."
    systemctl enable raspotify.service
    echo "✓ Raspotify service enabled"
fi
echo ""

# Summary
echo "=== Installation Complete ==="
echo ""
echo "Services installed and enabled for autostart on boot:"
echo "  1. srs-server.service   - SRS RTMP/HTTP-FLV server (Docker)"
echo "  2. hsg-canvas.service   - HSG Canvas web app"
echo "  3. raspotify.service    - Spotify Connect client"
echo ""
echo "Service startup order:"
echo "  1. Docker service"
echo "  2. SRS Server (depends on Docker)"
echo "  3. HSG Canvas (depends on SRS Server)"
echo "  4. Raspotify (independent)"
echo ""
echo "To start all services now without rebooting:"
echo "  sudo systemctl start srs-server"
echo "  sudo systemctl start hsg-canvas"
echo "  sudo systemctl start raspotify"
echo ""
echo "To check service status:"
echo "  sudo systemctl status srs-server"
echo "  sudo systemctl status hsg-canvas"
echo "  sudo systemctl status raspotify"
echo ""
echo "To view logs:"
echo "  sudo journalctl -u srs-server -f"
echo "  sudo journalctl -u hsg-canvas -f"
echo "  sudo journalctl -u raspotify -f"
echo ""
echo "The services will now start automatically on boot!"
