#!/bin/bash
# System information for troubleshooting

echo "Pi4 System Information for Stream Controller"
echo "============================================"
echo ""

echo "🖥️  System:"
echo "   Model: $(cat /proc/cpuinfo | grep Model | head -1 | cut -d: -f2 | xargs)"
echo "   Kernel: $(uname -r)"
echo "   OS: $(lsb_release -d | cut -f2)"
echo ""

echo "🎮 GPU Configuration:"
echo "   GPU Memory: $(vcgencmd get_mem gpu)"
echo "   ARM Memory: $(vcgencmd get_mem arm)"
echo "   GPU Temperature: $(vcgencmd measure_temp)"
echo "   Core Frequency: $(vcgencmd measure_clock core | cut -d= -f2 | awk '{print $1/1000000 " MHz"}')"
echo ""

echo "🔧 DRM Information:"
if command -v drm_info >/dev/null 2>&1; then
    drm_info 2>/dev/null | head -20
else
    echo "   drm_info not available"
    if [ -d "/dev/dri" ]; then
        echo "   DRM devices:"
        ls -la /dev/dri/
    fi
fi
echo ""

echo "📺 Display Connectors:"
for connector in /sys/class/drm/card0-*/status; do
    if [ -f "$connector" ]; then
        connector_name=$(basename $(dirname $connector) | sed 's/card0-//')
        status=$(cat $connector)
        echo "   $connector_name: $status"
    fi
done
echo ""

echo "🎬 Available Video Devices:"
for device in /dev/video*; do
    if [ -c "$device" ]; then
        echo "   $device"
    fi
done
echo ""

echo "👤 User Information:"
echo "   User: $USER"
echo "   Groups: $(groups)"
echo "   UID: $(id -u)"
echo "   GID: $(id -g)"
echo ""

echo "📦 Key Package Versions:"
mpv --version 2>/dev/null | head -1 || echo "   MPV: Not installed"
ffmpeg -version 2>/dev/null | head -1 || echo "   FFmpeg: Not installed"
python3 --version || echo "   Python3: Not installed"
echo ""

echo "⚙️  Boot Configuration (/boot/config.txt):"
echo "   GPU Memory: $(grep gpu_mem /boot/config.txt | tail -1 || echo 'Not set')"
echo "   DRM Driver: $(grep vc4-kms-v3d /boot/config.txt | tail -1 || echo 'Not set')"
echo "   GPU Freq: $(grep gpu_freq /boot/config.txt | tail -1 || echo 'Not set')"
