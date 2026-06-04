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
ACTUAL_GROUP=$(id -gn "$ACTUAL_USER")
ACTUAL_UID=$(id -u "$ACTUAL_USER")
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

echo -e "${YELLOW}Installing for user: $ACTUAL_USER (group: $ACTUAL_GROUP, uid: $ACTUAL_UID)${NC}"
echo -e "${YELLOW}Home directory: $USER_HOME${NC}"
echo -e "${YELLOW}Script directory: $SCRIPT_DIR${NC}"
echo ""

# Render a systemd unit / drop-in from the repo, substituting the canonical
# hsg deployment values (user, home, repo path, uid) with this install's.
# Keeps the checked-in files readable as the hsg reference while letting the
# canvas install under any user/path.
render_unit() {
    # render_unit <src> <dest>
    sed -e "s#/home/hsg/srs_server#$SCRIPT_DIR#g" \
        -e "s#/home/hsg#$USER_HOME#g" \
        -e "s#^User=hsg\$#User=$ACTUAL_USER#" \
        -e "s#^Group=hsg\$#Group=$ACTUAL_GROUP#" \
        -e "s#/run/user/1000#/run/user/$ACTUAL_UID#g" \
        "$1" > "$2"
}

# ============================================
# 0. Hostname / mDNS name
# ============================================
# CANVAS_HOST drives the system hostname and the mDNS name the kiosk loads
# (http://<CANVAS_HOST>.local/canvas/). Resolution: env var, then canvas.conf,
# then default "canvas". Persist the choice to canvas.conf so the Python app
# (config.py) reads the same value.
CANVAS_CONF="$SCRIPT_DIR/canvas.conf"
ENV_CANVAS_HOST="${CANVAS_HOST:-}"   # explicit override, if the operator set one
if [ -z "${CANVAS_HOST:-}" ] && [ -f "$CANVAS_CONF" ]; then
    # Take the value after '=', strip surrounding quotes and whitespace/CR.
    CANVAS_HOST=$(sed -n 's/^CANVAS_HOST=//p' "$CANVAS_CONF" | head -1 | sed "s/[\"' ]//g; s/\r//g")
fi
CANVAS_HOST="${CANVAS_HOST:-canvas}"
# Persist when canvas.conf is missing, OR when an explicit env override was
# given — otherwise re-running `CANVAS_HOST=newname ./setup.sh` would change the
# system hostname but leave config.py reading the old name from canvas.conf.
if [ ! -f "$CANVAS_CONF" ] || [ -n "$ENV_CANVAS_HOST" ]; then
    echo "CANVAS_HOST=$CANVAS_HOST" > "$CANVAS_CONF"
    chown $ACTUAL_USER:$ACTUAL_GROUP "$CANVAS_CONF"
fi

echo -e "${BLUE}[0/8] Setting hostname to '$CANVAS_HOST'...${NC}"
CURRENT_HOST=$(hostname)
if [ "$CURRENT_HOST" != "$CANVAS_HOST" ]; then
    hostnamectl set-hostname "$CANVAS_HOST"
    # Keep /etc/hosts in sync so sudo/local name resolution doesn't warn
    sed -i "s/\b$CURRENT_HOST\b/$CANVAS_HOST/g" /etc/hosts
    grep -q "127.0.1.1[[:space:]]\+$CANVAS_HOST" /etc/hosts || \
        echo "127.0.1.1	$CANVAS_HOST" >> /etc/hosts
    # avahi-daemon publishes <hostname>.local; restart so the new name is live
    systemctl restart avahi-daemon 2>/dev/null || true
    echo -e "${GREEN}✓ Hostname set to $CANVAS_HOST (was $CURRENT_HOST) → ${CANVAS_HOST}.local${NC}"
else
    echo -e "${GREEN}✓ Hostname already $CANVAS_HOST${NC}"
fi
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
    libportaudio2 \
    feh \
    jq \
    bc \
    sysstat \
    bluez \
    libspa-0.2-bluetooth \
    python3-dbus \
    python3-gi \
    dbus \
    nodejs \
    npm \
    cage \
    seatd

# The kiosk renders via cage (wlroots) straight to DRM, using seatd to acquire
# the seat without a logind graphical session. Both are required for headless
# kiosk output and were previously assumed pre-installed.
systemctl enable seatd.service
# GPU/DRM access for the kiosk user, plus seatd's socket group if it exists.
usermod -aG render,video "$ACTUAL_USER"
getent group _seatd >/dev/null && usermod -aG _seatd "$ACTUAL_USER" || true
getent group seat   >/dev/null && usermod -aG seat   "$ACTUAL_USER" || true

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
cat > /etc/raspotify/conf << EOF
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

# Onevent hook - forward Spotify events to HSG Canvas API
LIBRESPOT_ONEVENT=$SCRIPT_DIR/raspotify-onevent.sh
EOF

# Install systemd drop-in for PipeWire/PulseAudio access
# Raspotify's default sandbox (PrivateUsers, ProtectHome) blocks PulseAudio sockets
mkdir -p /etc/systemd/system/raspotify.service.d
render_unit "$SCRIPT_DIR/config/raspotify/onevent.conf" /etc/systemd/system/raspotify.service.d/onevent.conf

systemctl daemon-reload
systemctl enable raspotify.service
systemctl restart raspotify.service || true

echo -e "${GREEN}✓ Raspotify configured${NC}"
echo ""

# ============================================
# 3.5. Sendspin Daemon Installation
# ============================================
echo -e "${BLUE}[3.5/9] Installing Sendspin audio daemon...${NC}"

# Install uv if not present. It installs into the user's ~/.local/bin, which is
# NOT on sudo's reset PATH, so always invoke it by absolute path ($UV_BIN).
UV_BIN="$USER_HOME/.local/bin/uv"
if [ ! -x "$UV_BIN" ]; then
    echo "Installing uv..."
    sudo -u $ACTUAL_USER sh -c 'curl -LsSf https://astral.sh/uv/install.sh | sh'
fi

# Install Python 3.13 via uv (prebuilt binary, no compilation)
echo "Ensuring Python 3.13 is available..."
sudo -u $ACTUAL_USER "$UV_BIN" python install 3.13

# Sendspin daemon identity / output device (override via env when running
# setup.sh, e.g. SENDSPIN_NAME="Kenwood Speakers" SENDSPIN_AUDIO_DEVICE=pipewire).
SENDSPIN_NAME="${SENDSPIN_NAME:-HSG Canvas}"
SENDSPIN_ID="${SENDSPIN_ID:-$(echo "$SENDSPIN_NAME" | tr '[:upper:] ' '[:lower:]-')}"
# 'pulse' routes through the PipeWire/PulseAudio sound server to the default
# sink (the DAC). NB: sendspin's portaudio backend exposes 'pulse'/'default',
# not 'pipewire' — the latter errors with "Audio device not found".
SENDSPIN_AUDIO_DEVICE="${SENDSPIN_AUDIO_DEVICE:-pulse}"

# Install/upgrade the sendspin CLI to the latest release. The hook-based daemon
# (--hook-start/--hook-stop) the canvas relies on for display/audio coordination
# needs a modern sendspin; older installs (e.g. 1.x) have a flat CLI with no
# daemon subcommand or hooks at all.
echo "Installing/upgrading sendspin CLI to latest..."
sudo -u $ACTUAL_USER "$UV_BIN" tool install sendspin@latest --python 3.13 --force

# A user-level sendspin.service would fight this system daemon over the audio
# device and the Music Assistant registration — disable it if present.
if [ -f "$USER_HOME/.config/systemd/user/sendspin.service" ]; then
    sudo -u $ACTUAL_USER \
        XDG_RUNTIME_DIR=/run/user/$ACTUAL_UID \
        DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$ACTUAL_UID/bus \
        systemctl --user disable --now sendspin.service 2>/dev/null || true
    echo "  Disabled conflicting user-level sendspin.service"
fi

# Create sendspin config directory and settings
mkdir -p "$USER_HOME/.config/sendspin"
cat > "$USER_HOME/.config/sendspin/settings-daemon.json" << EOF
{
    "name": "$SENDSPIN_NAME",
    "client_id": "$SENDSPIN_ID"
}
EOF
chown -R $ACTUAL_USER:$ACTUAL_USER "$USER_HOME/.config/sendspin"

# Install systemd service for sendspin daemon. uv tool installs the launcher
# into ~/.local/bin (not on sudo's PATH), so reference it by absolute path.
SENDSPIN_BIN="$USER_HOME/.local/bin/sendspin"
if [ -x "$SENDSPIN_BIN" ]; then
    cat > /etc/systemd/system/sendspin.service << SVCEOF
[Unit]
Description=Sendspin Multi-Room Audio Client
After=network-online.target sound.target pipewire.service
Wants=network-online.target

[Service]
Type=simple
User=$ACTUAL_USER
Environment=XDG_RUNTIME_DIR=/run/user/$(id -u $ACTUAL_USER)
Environment=DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$(id -u $ACTUAL_USER)/bus
ExecStart=$SENDSPIN_BIN daemon --name "$SENDSPIN_NAME" --id "$SENDSPIN_ID" --audio-device "$SENDSPIN_AUDIO_DEVICE" --hook-start "curl -s -X POST http://127.0.0.1:8000/sendspin/hook/start" --hook-stop "curl -s -X POST http://127.0.0.1:8000/sendspin/hook/stop"
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
SVCEOF

    systemctl daemon-reload
    systemctl enable sendspin.service
    systemctl start sendspin.service || true
    echo -e "${GREEN}✓ Sendspin daemon installed and started${NC}"
else
    echo -e "${YELLOW}⚠ sendspin binary not found, skipping systemd service${NC}"
fi

echo ""

# ============================================
# 3.6. Bluetooth A2DP Sink Setup
# ============================================
echo -e "${BLUE}[3.6/9] Setting up Bluetooth A2DP sink...${NC}"

# Configure BlueZ for auto-pairable audio sink
if [ -f /etc/bluetooth/main.conf ]; then
    sed -i 's/^#\?Name\s*=.*/Name = HSG Canvas/' /etc/bluetooth/main.conf
    sed -i 's/^#\?DiscoverableTimeout\s*=.*/DiscoverableTimeout = 0/' /etc/bluetooth/main.conf
    sed -i 's/^#\?Pairable\s*=.*/Pairable = true/' /etc/bluetooth/main.conf
    sed -i 's/^#\?AutoEnable\s*=.*/AutoEnable = true/' /etc/bluetooth/main.conf

    # Set device class to Audio/Video Loudspeaker
    if grep -q '^\[General\]' /etc/bluetooth/main.conf; then
        if ! grep -q '^Class\s*=' /etc/bluetooth/main.conf; then
            sed -i '/^\[General\]/a Class = 0x200414' /etc/bluetooth/main.conf
        else
            sed -i 's/^Class\s*=.*/Class = 0x200414/' /etc/bluetooth/main.conf
        fi
    fi
fi

# Install auto-accept pairing agent (replaces bluez-tools bt-agent)
chmod +x "$SCRIPT_DIR/config/bluetooth/bt-auto-agent.py"
render_unit "$SCRIPT_DIR/config/bluetooth/bt-auto-agent.service" /etc/systemd/system/bt-auto-agent.service

# Remove old bt-agent service if it exists
systemctl disable bt-agent.service 2>/dev/null || true
systemctl stop bt-agent.service 2>/dev/null || true
rm -f /etc/systemd/system/bt-agent.service

# WirePlumber config: route incoming BT A2DP audio to speakers
BT_WP_DIR="$USER_HOME/.config/wireplumber/bluetooth.lua.d"
mkdir -p "$BT_WP_DIR"
cp "$SCRIPT_DIR/config/bluetooth/51-hsg-bluetooth.lua" "$BT_WP_DIR/51-hsg-bluetooth.lua"
chown -R $ACTUAL_USER:$ACTUAL_USER "$USER_HOME/.config/wireplumber"

systemctl daemon-reload
systemctl enable bluetooth.service
systemctl restart bluetooth.service || true
sleep 2
# Set the advertised name (Alias) — Name in main.conf is the system hostname, Alias is what phones see
bluetoothctl system-alias "HSG Canvas" || true
systemctl enable bt-auto-agent.service
systemctl start bt-auto-agent.service || true

echo -e "${GREEN}✓ Bluetooth A2DP sink configured${NC}"
echo ""

# ============================================
# 4. Audio Configuration (PipeWire/PulseAudio)
# ============================================
echo -e "${BLUE}[4/8] Configuring audio system...${NC}"

# Detect the RPi DAC Pro (CARD=3)
DAC_DEVICE=$(aplay -l | grep -oP 'card \K3(?=.*RPi DAC Pro)' | head -1 || echo "")

if [ -n "$DAC_DEVICE" ]; then
    echo "Found RPi DAC Pro on CARD=$DAC_DEVICE"

    # Find the PipeWire/PulseAudio sink backed by the DAC. The sink name varies
    # by board/kernel, so detect it from the sink description rather than
    # hardcoding (sendspin/raspotify/browser all route here via the sound server).
    USER_RUNTIME="/run/user/$ACTUAL_UID"
    DAC_SINK=$(sudo -u $ACTUAL_USER XDG_RUNTIME_DIR=$USER_RUNTIME pactl list sinks 2>/dev/null | \
        awk '/^[[:space:]]*Name: /{n=$2} /RPi DAC Pro|pcm512/{print n; exit}')
    [ -z "$DAC_SINK" ] && DAC_SINK="alsa_output.platform-soc_sound.stereo-fallback"
    echo "Using DAC sink: $DAC_SINK"

    # Set default sink + full volume on the running session
    sudo -u $ACTUAL_USER XDG_RUNTIME_DIR=$USER_RUNTIME bash << USEREOF
        sleep 2
        pactl set-default-sink "$DAC_SINK" 2>/dev/null || true
        pactl set-sink-volume "$DAC_SINK" 100% 2>/dev/null || true
USEREOF

    # Persist the default sink across reboots
    mkdir -p "$USER_HOME/.config/pipewire/pipewire.conf.d"
    cat > "$USER_HOME/.config/pipewire/pipewire.conf.d/99-default-sink.conf" << EOF
# HSG Canvas - Default audio sink configuration
context.exec = [
    { path = "pactl" args = "set-default-sink $DAC_SINK" }
]
EOF
    chown -R $ACTUAL_USER:$ACTUAL_USER "$USER_HOME/.config/pipewire"

    echo -e "${GREEN}✓ Audio configured for RPi DAC Pro ($DAC_SINK)${NC}"
else
    echo -e "${YELLOW}⚠ RPi DAC Pro not detected, using default audio device${NC}"
fi

# Larger audio buffer so playback survives CPU/thermal-throttle spikes (Pi
# drops out at ~82C with the default 1024 quantum). Applies regardless of DAC.
mkdir -p "$USER_HOME/.config/pipewire/pipewire.conf.d"
cp "$SCRIPT_DIR/config/pipewire-99-kiosk-buffer.conf" "$USER_HOME/.config/pipewire/pipewire.conf.d/99-kiosk-buffer.conf"
chown -R $ACTUAL_USER:$ACTUAL_USER "$USER_HOME/.config/pipewire"
echo -e "${GREEN}✓ PipeWire buffer (2048 quantum) configured${NC}"

echo ""

# ============================================
# 5. Python Virtual Environment Setup
# ============================================
echo -e "${BLUE}[5/8] Setting up Python virtual environment...${NC}"

cd "$SCRIPT_DIR"

# Create venv with Python 3.13 via uv (required for aiosendspin)
if [ -d ".venv" ]; then
    VENV_PY=$(.venv/bin/python --version 2>/dev/null || echo "")
    if echo "$VENV_PY" | grep -q "3.13"; then
        echo -e "${GREEN}✓ Virtual environment already exists (Python 3.13)${NC}"
    else
        echo "Recreating venv with Python 3.13 (was: $VENV_PY)..."
        rm -rf .venv
        sudo -u $ACTUAL_USER "$UV_BIN" venv --python 3.13 .venv
        echo -e "${GREEN}✓ Virtual environment recreated with Python 3.13${NC}"
    fi
else
    sudo -u $ACTUAL_USER "$UV_BIN" venv --python 3.13 .venv
    echo -e "${GREEN}✓ Virtual environment created (Python 3.13)${NC}"
fi

# Install Python dependencies via uv
sudo -u $ACTUAL_USER "$UV_BIN" pip install --python .venv/bin/python -r requirements.txt

echo -e "${GREEN}✓ Python dependencies installed${NC}"
echo ""

# Build the React canvas (production bundle, served by FastAPI from frontend/dist)
echo -e "${BLUE}[5b] Building React canvas...${NC}"
cd "$SCRIPT_DIR/frontend"
sudo -u $ACTUAL_USER npm ci
sudo -u $ACTUAL_USER npm run build
cd "$SCRIPT_DIR"
echo -e "${GREEN}✓ React canvas built${NC}"
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
# 7. Install Angie Reverse Proxy
# ============================================
echo -e "${BLUE}[7/9] Installing Angie reverse proxy...${NC}"

if ! command -v angie &> /dev/null; then
    curl -o /etc/apt/trusted.gpg.d/angie-signing.gpg https://angie.software/keys/angie-signing.gpg
    echo "deb https://download.angie.software/angie/$(. /etc/os-release && echo "$ID/$VERSION_ID $VERSION_CODENAME") main" \
        > /etc/apt/sources.list.d/angie.list
    apt-get update && apt-get install -y angie
    echo -e "${GREEN}  ✓ Angie installed${NC}"
else
    echo -e "${GREEN}  ✓ Angie already installed${NC}"
fi

# Remove default config, symlink ours
rm -f /etc/angie/http.d/default.conf
ln -sf "$SCRIPT_DIR/config/angie/hsg-canvas.conf" /etc/angie/http.d/hsg-canvas.conf

# Loading splash Angie serves on upstream 502/503/504 while FastAPI starts
# (fixed path, referenced by hsg-canvas.conf which is symlinked, not rendered).
cp "$SCRIPT_DIR/config/angie/loading.html" /etc/angie/hsg-loading.html

systemctl enable angie
systemctl start angie || systemctl restart angie

echo -e "${GREEN}✓ Angie configured and running${NC}"
echo ""

# ============================================
# 8. Install Systemd Services
# ============================================
echo -e "${BLUE}[8/9] Installing systemd services...${NC}"

# Install SRS Server service
render_unit "$SCRIPT_DIR/srs-server.service" /etc/systemd/system/srs-server.service
echo "  ✓ srs-server.service"

# Install HSG Canvas service (from config/ directory)
render_unit "$SCRIPT_DIR/config/hsg-canvas.service" /etc/systemd/system/hsg-canvas.service
echo "  ✓ hsg-canvas.service"

# Reload systemd
systemctl daemon-reload

# Enable services (don't start yet)
systemctl enable srs-server.service
systemctl enable hsg-canvas.service
systemctl enable raspotify.service

# Install sudoers drop-in so the hsg-canvas watchdog can restart raspotify
# when librespot wedges (auth/rate-limit errors or silent zombie state).
sed "s#^hsg ALL#$ACTUAL_USER ALL#" \
    "$SCRIPT_DIR/config/sudoers.d/hsg-canvas" > /etc/sudoers.d/hsg-canvas
chown root:root /etc/sudoers.d/hsg-canvas
chmod 0440 /etc/sudoers.d/hsg-canvas
visudo -c -f /etc/sudoers.d/hsg-canvas
echo "  ✓ /etc/sudoers.d/hsg-canvas"

echo -e "${GREEN}✓ Services installed and enabled${NC}"
echo ""

# ============================================
# 8.5. Kiosk mode — let the canvas own the display
# ============================================
echo -e "${BLUE}[8.5/9] Configuring kiosk mode...${NC}"
# The canvas renders via cage straight to DRM on the foreground VT. For that to
# work on boot it must own the seat:
#   - no display manager / desktop compositor holding the GPU
#   - boot to multi-user (no graphical.target)
#   - no getty on tty1 competing for the foreground VT (logind-vs-seatd)
#   - the user's PipeWire session running without a graphical login (linger),
#     since hsg-canvas + sendspin run as system services that talk to it.
for dm in lightdm gdm gdm3 sddm; do
    systemctl disable "$dm" 2>/dev/null && echo "  disabled $dm" || true
done
systemctl set-default multi-user.target
systemctl mask getty@tty1
loginctl enable-linger "$ACTUAL_USER"
echo -e "${GREEN}✓ Kiosk mode configured (multi-user, getty@tty1 masked, linger on)${NC}"
echo ""

# ============================================
# 9. Set Permissions
# ============================================
echo -e "${BLUE}[9/9] Setting permissions...${NC}"

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
echo "  4. sendspin.service     - Sendspin multi-room audio receiver"
echo "  5. bt-auto-agent.service - Bluetooth auto-accept pairing agent"
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
echo "   sudo systemctl status sendspin"
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
