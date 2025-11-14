#!/bin/bash

# HSG Canvas Full System Setup Script
# Sets up a fresh Raspberry Pi with all components for HSG Canvas
#
# Run as: sudo ./setup.sh

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  HSG Canvas - Full System Setup${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Check if running with sudo
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}Please run with sudo: sudo ./setup.sh${NC}"
    exit 1
fi

# Get the actual user (not root when using sudo)
ACTUAL_USER=${SUDO_USER:-$USER}
USER_HOME=$(eval echo ~$ACTUAL_USER)
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

echo -e "${YELLOW}Installing for user: $ACTUAL_USER${NC}"
echo -e "${YELLOW}Home directory: $USER_HOME${NC}"
echo -e "${YELLOW}Script directory: $SCRIPT_DIR${NC}"
echo ""

# ============================================
# 1. System Package Installation
# ============================================
echo -e "${BLUE}[1/8] Installing system packages...${NC}"

apt-get update
apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    ffmpeg \
    mpv \
    docker.io \
    docker-compose \
    git \
    curl \
    wget \
    pipewire \
    pipewire-pulse \
    wireplumber \
    alsa-utils \
    pulseaudio-utils \
    feh \
    jq \
    bc \
    sysstat

echo -e "${GREEN}✓ System packages installed${NC}"
echo ""

# ============================================
# 2. Docker Setup
# ============================================
echo -e "${BLUE}[2/8] Setting up Docker...${NC}"

# Add user to docker group
usermod -aG docker $ACTUAL_USER

# Enable Docker service
systemctl enable docker.service
systemctl start docker.service || true

echo -e "${GREEN}✓ Docker configured${NC}"
echo ""

# ============================================
# 3. Raspotify Installation & Configuration
# ============================================
echo -e "${BLUE}[3/8] Installing Raspotify...${NC}"

if ! command -v librespot &> /dev/null; then
    echo "Installing Raspotify..."
    curl -sL https://dtcooper.github.io/raspotify/install.sh | sh
    echo -e "${GREEN}✓ Raspotify installed${NC}"
else
    echo -e "${GREEN}✓ Raspotify already installed${NC}"
fi

# Configure Raspotify for PulseAudio/PipeWire
echo "Configuring Raspotify..."
cat > /etc/raspotify/conf << 'EOF'
# HSG Canvas Raspotify Configuration

# Audio Backend - Use PulseAudio (works with PipeWire compatibility layer)
LIBRESPOT_BACKEND=pulseaudio

# Audio Quality
LIBRESPOT_BITRATE=320

# Device Info
LIBRESPOT_DEVICE_TYPE=speaker
LIBRESPOT_NAME="HSG Canvas"

# Volume Settings
LIBRESPOT_INITIAL_VOLUME=70
LIBRESPOT_ENABLE_VOLUME_NORMALISATION=

# Cache Settings (cleared for fresh auth)
LIBRESPOT_DISABLE_AUDIO_CACHE=
LIBRESPOT_DISABLE_CREDENTIAL_CACHE=

# Temp Directory
TMPDIR=/tmp
EOF

systemctl enable raspotify.service
systemctl restart raspotify.service || true

echo -e "${GREEN}✓ Raspotify configured${NC}"
echo ""

# ============================================
# 4. Audio Configuration (PipeWire/PulseAudio)
# ============================================
echo -e "${BLUE}[4/8] Configuring audio system...${NC}"

# Detect the RPi DAC Pro (CARD=3)
DAC_DEVICE=$(aplay -l | grep -oP 'card \K3(?=.*RPi DAC Pro)' | head -1 || echo "")

if [ -n "$DAC_DEVICE" ]; then
    echo "Found RPi DAC Pro on CARD=$DAC_DEVICE"

    # Set default PulseAudio/PipeWire sink to DAC Pro
    # This is run as the actual user, not root
    sudo -u $ACTUAL_USER bash << USEREOF
        # Wait for PipeWire to be ready
        sleep 2

        # Set default sink
        pactl set-default-sink alsa_output.platform-soc_sound.stereo-fallback 2>/dev/null || true

        # Set volume to 100%
        pactl set-sink-volume alsa_output.platform-soc_sound.stereo-fallback 100% 2>/dev/null || true
USEREOF

    # Create persistent configuration for user
    mkdir -p "$USER_HOME/.config/pipewire/pipewire.conf.d"
    cat > "$USER_HOME/.config/pipewire/pipewire.conf.d/99-default-sink.conf" << 'EOF'
# HSG Canvas - Default audio sink configuration
context.exec = [
    { path = "pactl" args = "set-default-sink alsa_output.platform-soc_sound.stereo-fallback" }
]
EOF
    chown -R $ACTUAL_USER:$ACTUAL_USER "$USER_HOME/.config/pipewire"

    echo -e "${GREEN}✓ Audio configured for RPi DAC Pro${NC}"
else
    echo -e "${YELLOW}⚠ RPi DAC Pro not detected, using default audio device${NC}"
fi

echo ""

# ============================================
# 5. Python Virtual Environment Setup
# ============================================
echo -e "${BLUE}[5/8] Setting up Python virtual environment...${NC}"

cd "$SCRIPT_DIR"

# Create venv if it doesn't exist
if [ ! -d ".venv" ]; then
    sudo -u $ACTUAL_USER python3 -m venv .venv
    echo -e "${GREEN}✓ Virtual environment created${NC}"
else
    echo -e "${GREEN}✓ Virtual environment already exists${NC}"
fi

# Install Python dependencies
sudo -u $ACTUAL_USER bash << 'USEREOF'
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
# Upgrade yt-dlp to latest version (critical for YouTube playback with anti-bot measures)
pip install --upgrade yt-dlp
deactivate
USEREOF

echo -e "${GREEN}✓ Python dependencies installed${NC}"
echo -e "${GREEN}✓ yt-dlp upgraded to latest version${NC}"
echo ""

# ============================================
# 6. SRS Server Setup (Docker)
# ============================================
echo -e "${BLUE}[6/8] Setting up SRS Server...${NC}"

# Pull SRS Docker image
docker pull ossrs/srs:5

echo -e "${GREEN}✓ SRS Server image pulled${NC}"
echo ""

# ============================================
# 7. Install Systemd Services
# ============================================
echo -e "${BLUE}[7/8] Installing systemd services...${NC}"

# Install SRS Server service
cp "$SCRIPT_DIR/srs-server.service" /etc/systemd/system/
echo "  ✓ srs-server.service"

# Install HSG Canvas service
cp "$SCRIPT_DIR/hsg-canvas.service" /etc/systemd/system/
echo "  ✓ hsg-canvas.service"

# Reload systemd
systemctl daemon-reload

# Enable services (don't start yet)
systemctl enable srs-server.service
systemctl enable hsg-canvas.service
systemctl enable raspotify.service

echo -e "${GREEN}✓ Services installed and enabled${NC}"
echo ""

# ============================================
# 8. Set Permissions
# ============================================
echo -e "${BLUE}[8/8] Setting permissions...${NC}"

# Make scripts executable
chmod +x "$SCRIPT_DIR/start.sh"
chmod +x "$SCRIPT_DIR/monitor.sh"
chmod +x "$SCRIPT_DIR/install-services.sh"

# Set ownership
chown -R $ACTUAL_USER:$ACTUAL_USER "$SCRIPT_DIR"

echo -e "${GREEN}✓ Permissions configured${NC}"
echo ""

# ============================================
# Installation Complete
# ============================================
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Installation Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

echo -e "${YELLOW}Installed Services:${NC}"
echo "  1. srs-server.service   - SRS RTMP/HTTP-FLV server (Docker)"
echo "  2. hsg-canvas.service   - HSG Canvas web app"
echo "  3. raspotify.service    - Spotify Connect client"
echo ""

echo -e "${YELLOW}Next Steps:${NC}"
echo ""
echo "1. ${BLUE}Reboot your Raspberry Pi:${NC}"
echo "   sudo reboot"
echo ""
echo "2. ${BLUE}After reboot, verify services are running:${NC}"
echo "   sudo systemctl status srs-server"
echo "   sudo systemctl status hsg-canvas"
echo "   sudo systemctl status raspotify"
echo ""
echo "3. ${BLUE}Monitor system status:${NC}"
echo "   ./monitor.sh          # Run once"
echo "   ./monitor.sh -w       # Watch mode (live updates)"
echo ""
echo "4. ${BLUE}Access the web interface:${NC}"
echo "   http://$(hostname -I | awk '{print $1}')"
echo "   or"
echo "   http://localhost"
echo ""
echo "5. ${BLUE}Connect Spotify:${NC}"
echo "   - Open Spotify app on your phone"
echo "   - Start playing music"
echo "   - Tap 'Devices Available' icon"
echo "   - Select 'HSG Canvas'"
echo ""

echo -e "${YELLOW}Useful Commands:${NC}"
echo "  View logs:    sudo journalctl -u hsg-canvas -f"
echo "  Restart:      sudo systemctl restart hsg-canvas"
echo "  Stop:         sudo systemctl stop hsg-canvas"
echo "  Check status: ./monitor.sh"
echo ""

echo -e "${GREEN}Setup complete! Please reboot to start all services.${NC}"
echo ""
