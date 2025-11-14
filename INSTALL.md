# HSG Canvas - Installation Guide

Complete setup guide for installing HSG Canvas on a fresh Raspberry Pi.

## Prerequisites

- Raspberry Pi 4 or newer (recommended)
- Raspberry Pi OS (Bookworm or newer)
- Internet connection
- RPi DAC Pro or compatible audio hardware (optional but recommended)
- Spotify Premium account (for Spotify Connect feature)

## Quick Installation

### 1. Clone the Repository

```bash
git clone <repository-url>
cd srs_server
```

### 2. Run the Setup Script

```bash
sudo ./setup.sh
```

This automated script will:
- ✅ Install all system dependencies (Python, FFmpeg, MPV, Docker, etc.)
- ✅ Set up Docker and SRS Server
- ✅ Install and configure Raspotify (Spotify Connect)
- ✅ Configure audio system (PipeWire/PulseAudio with RPi DAC Pro)
- ✅ Create Python virtual environment and install dependencies
- ✅ Install and enable systemd services for auto-start on boot
- ✅ Set proper permissions

### 3. Reboot

```bash
sudo reboot
```

### 4. Verify Installation

After reboot, check that all services are running:

```bash
./monitor.sh
```

Or check individual services:

```bash
sudo systemctl status srs-server
sudo systemctl status hsg-canvas
sudo systemctl status raspotify
```

## What Gets Installed

### System Packages
- **Python 3** - Runtime for the web application
- **FFmpeg** - Media processing and streaming
- **MPV** - Video/audio playback
- **Docker** - Container runtime for SRS Server
- **PipeWire/PulseAudio** - Audio system
- **ALSA Utils** - Audio device management
- **Utilities** - feh, jq, bc, sysstat, etc.

### Services

#### 1. SRS Server (`srs-server.service`)
- RTMP/HTTP-FLV streaming server
- Runs in Docker container
- Listens on:
  - RTMP: `rtmp://localhost:1935`
  - HTTP-FLV: `http://localhost:8080`
  - API: `http://localhost:1985`

#### 2. HSG Canvas (`hsg-canvas.service`)
- Main web application
- Listens on `http://localhost:80`
- Features:
  - Stream republishing
  - YouTube playback
  - Image/QR code display
  - System monitoring

#### 3. Raspotify (`raspotify.service`)
- Spotify Connect client
- Device name: "HSG Canvas"
- Quality: 320 kbps
- Uses PulseAudio backend

### Audio Configuration

The setup script automatically:
- Detects RPi DAC Pro (CARD=3)
- Sets it as the default audio output
- Configures volume to 100%
- Creates persistent PipeWire configuration
- Configures Raspotify to use the correct audio device

## Manual Configuration (Optional)

### Change Spotify Device Name

Edit `/etc/raspotify/conf`:
```bash
sudo nano /etc/raspotify/conf
```

Change this line:
```bash
LIBRESPOT_NAME="HSG Canvas"
```

Restart Raspotify:
```bash
sudo systemctl restart raspotify
```

### Change Web App Port

Edit `/etc/systemd/system/hsg-canvas.service`:
```bash
sudo nano /etc/systemd/system/hsg-canvas.service
```

Change `--port 80` to your desired port, then:
```bash
sudo systemctl daemon-reload
sudo systemctl restart hsg-canvas
```

### Configure Audio Device

If you're not using RPi DAC Pro, identify your audio device:
```bash
aplay -l
```

Update PipeWire default sink:
```bash
pactl list sinks short
pactl set-default-sink <your-sink-name>
```

## Troubleshooting

### Services Not Starting

Check service status:
```bash
sudo systemctl status hsg-canvas
sudo journalctl -u hsg-canvas -n 50
```

### No Audio from Spotify

1. Check Raspotify is running:
   ```bash
   systemctl status raspotify
   ```

2. Verify audio device:
   ```bash
   pactl list sinks
   ```

3. Check default sink:
   ```bash
   pactl info | grep "Default Sink"
   ```

4. Restart Raspotify:
   ```bash
   sudo systemctl restart raspotify
   ```

### Web Interface Not Accessible

1. Check if service is running:
   ```bash
   sudo systemctl status hsg-canvas
   ```

2. Check port binding:
   ```bash
   sudo netstat -tlnp | grep python
   ```

3. Check logs:
   ```bash
   sudo journalctl -u hsg-canvas -f
   ```

### Docker/SRS Issues

1. Verify Docker is running:
   ```bash
   sudo systemctl status docker
   ```

2. Check SRS container:
   ```bash
   docker ps | grep srs
   ```

3. View SRS logs:
   ```bash
   sudo journalctl -u srs-server -f
   ```

## Monitoring

Use the built-in monitoring script:

```bash
# Run once
./monitor.sh

# Live monitoring (refresh every 5 seconds)
./monitor.sh -w

# Custom refresh interval (e.g., 2 seconds)
./monitor.sh -w 2
```

The monitor shows:
- Service status (systemd)
- Process status (CPU, memory)
- API health
- System resources
- Temperature warnings

## Updating

To update the application:

```bash
git pull
source .venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart hsg-canvas
```

## Uninstallation

To remove services:

```bash
sudo systemctl stop srs-server hsg-canvas raspotify
sudo systemctl disable srs-server hsg-canvas raspotify
sudo rm /etc/systemd/system/srs-server.service
sudo rm /etc/systemd/system/hsg-canvas.service
sudo systemctl daemon-reload
```

To remove Raspotify:
```bash
sudo apt remove raspotify
```

To remove Docker and SRS:
```bash
docker stop srs-server
docker rm srs-server
docker rmi ossrs/srs:5
```

## Support

For issues or questions:
- Check the logs: `sudo journalctl -u hsg-canvas -f`
- Run diagnostics: `curl http://localhost/diagnostics`
- Use the monitor: `./monitor.sh`

## Features

Once installed, you can:
- **Stream media** to SRS server via RTMP
- **Play YouTube videos** with duration control
- **Display images and QR codes** on connected displays
- **Cast Spotify** from your phone (Premium required)
- **Monitor system** via web interface or CLI
- **Control playback** remotely via REST API

Access the web interface at: `http://<raspberry-pi-ip>/`
