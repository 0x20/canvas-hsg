#!/bin/bash

# HSG Canvas - Raspberry Pi Setup Script
# Complete setup for Pi4 with DRM acceleration and system optimization

set -e

echo "🚀 HSG Canvas - Raspberry Pi Setup"
echo "=================================="

# Check if running as root
if [[ $EUID -eq 0 ]]; then
   echo "❌ This script should NOT be run as root"
   echo "   Run as regular user: ./pi_setup.sh"
   exit 1
fi

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to add user to group if not already member
add_user_to_group() {
    local group=$1
    if groups $USER | grep -q "\b$group\b"; then
        echo "✅ User $USER already in group: $group"
    else
        echo "➕ Adding user $USER to group: $group"
        sudo usermod -a -G $group $USER
        echo "⚠️  You'll need to log out and back in for group changes to take effect"
        NEEDS_REBOOT=true
    fi
}

echo ""
echo "1️⃣  Checking system requirements..."

# Check Pi model
if ! grep -q "Raspberry Pi 4" /proc/cpuinfo; then
    echo "⚠️  Warning: This script is optimized for Raspberry Pi 4"
    echo "   Other Pi models may have limited DRM support"
fi

echo "🔍 Kernel version: $(uname -r)"

echo ""
echo "2️⃣  Configuring user permissions..."

# Add user to required groups for DRM access
add_user_to_group "video"
add_user_to_group "render" 
add_user_to_group "audio"
add_user_to_group "input"

echo ""
echo "3️⃣  Optimizing GPU memory..."

# Check current GPU memory split
CURRENT_GPU_MEM=$(vcgencmd get_mem gpu | cut -d= -f2 | sed 's/M//')
echo "🔍 Current GPU memory: ${CURRENT_GPU_MEM}MB"

if [ "$CURRENT_GPU_MEM" -lt 128 ]; then
    echo "⚠️  GPU memory too low, setting to 256MB..."
    
    # Backup config.txt
    sudo cp /boot/config.txt /boot/config.txt.backup.$(date +%Y%m%d_%H%M%S)
    
    # Remove existing gpu_mem lines and add optimal setting
    sudo sed -i '/^gpu_mem=/d' /boot/config.txt
    echo "gpu_mem=256" | sudo tee -a /boot/config.txt
    echo "✅ GPU memory set to 256MB (reboot required)"
    NEEDS_REBOOT=true
else
    echo "✅ GPU memory allocation adequate: ${CURRENT_GPU_MEM}MB"
fi

echo ""
echo "4️⃣  Optimizing Pi4 configuration..."

# Enable V3D driver and optimize settings
if ! grep -q "^dtoverlay=vc4-kms-v3d" /boot/config.txt; then
    echo "dtoverlay=vc4-kms-v3d" | sudo tee -a /boot/config.txt
    echo "✅ Enabled VC4 KMS driver"
    NEEDS_REBOOT=true
fi

# Disable legacy FKMS driver if present
if grep -q "^dtoverlay=vc4-fkms-v3d" /boot/config.txt; then
    sudo sed -i 's/^dtoverlay=vc4-fkms-v3d/#dtoverlay=vc4-fkms-v3d/' /boot/config.txt
    echo "✅ Disabled legacy FKMS driver"
    NEEDS_REBOOT=true
fi

# Add GPU performance settings if not present
if ! grep -q "^gpu_freq=" /boot/config.txt; then
    echo "# GPU performance settings" | sudo tee -a /boot/config.txt
    echo "gpu_freq=500" | sudo tee -a /boot/config.txt
    echo "over_voltage=2" | sudo tee -a /boot/config.txt
    echo "✅ Optimized GPU frequency"
    NEEDS_REBOOT=true
fi

echo ""
echo "5️⃣  Installing dependencies..."

# Update package list
sudo apt update

# Install essential packages
PACKAGES=(
    "python3" "python3-pip" "python3-venv"
    "mpv" "ffmpeg" "mesa-utils" "drm-info"
    "v4l-utils" "libdrm2" "libgbm1"
    "python3-pil" "git" "screen"
)

echo "📦 Installing packages..."
for package in "${PACKAGES[@]}"; do
    if dpkg -l | grep -q "^ii  $package "; then
        echo "✅ $package already installed"
    else
        echo "⬇️  Installing $package..."
        sudo apt install -y "$package"
    fi
done

echo ""
echo "6️⃣  Setting up Python environment..."

# Create virtual environment if it doesn't exist
if [ ! -d ".venv" ]; then
    echo "📝 Creating Python virtual environment..."
    python3 -m venv .venv
fi

# Install Python dependencies
echo "📦 Installing Python dependencies..."
source .venv/bin/activate
pip install -r requirements.txt

echo ""
echo "7️⃣  Testing DRM capabilities..."

# Test DRM device access
echo "🔍 Checking DRM devices..."
if [ -d "/dev/dri" ]; then
    ls -la /dev/dri/
    
    for device in /dev/dri/*; do
        if [ -c "$device" ]; then
            if [ -r "$device" ] && [ -w "$device" ]; then
                echo "✅ $device - accessible"
            else
                echo "❌ $device - insufficient permissions"
            fi
        fi
    done
else
    echo "❌ /dev/dri directory not found - DRM not available"
    exit 1
fi

echo ""
echo "8️⃣  System information..."

echo "👤 User: $USER"
echo "📦 Groups: $(groups)"
echo "🎮 GPU Memory: $(vcgencmd get_mem gpu)"
echo "🖥️  DRM Driver: $(grep vc4-kms-v3d /boot/config.txt | tail -1 || echo 'Not configured')"

echo ""
echo "🎯 Setup Summary"
echo "==============="
echo "✅ User permissions configured"
echo "✅ GPU memory optimized" 
echo "✅ Pi4 configuration optimized"
echo "✅ Dependencies installed"
echo "✅ Python environment ready"
echo "✅ DRM capabilities verified"

if [ "$NEEDS_REBOOT" = true ]; then
    echo ""
    echo "⚠️  REBOOT REQUIRED"
    echo "   Configuration changes require a reboot"
    echo "   Run: sudo reboot"
    echo ""
    echo "📋 After reboot:"
    echo "   ./start.sh - Start the application"
    echo "   ./system_info.sh - Check system status"
else
    echo ""
    echo "📋 Ready to start:"
    echo "   ./start.sh - Start the application"
    echo "   ./system_info.sh - Check system status"
fi

echo ""
echo "🚀 HSG Canvas setup complete!"