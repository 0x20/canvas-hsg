"""
HSG Canvas Configuration

Central configuration file for all constants and settings.
"""
import json
import os

# Base directory (for resolving relative paths)
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Paths
DEFAULT_BACKGROUND_PATH = os.path.join(_BASE_DIR, "canvas_background.png")

# Canvas instance hostname / mDNS domain.
# Resolution order: CANVAS_HOST env var, then `CANVAS_HOST=` in canvas.conf
# (repo root), then the default "canvas". The kiosk loads
# http://<CANVAS_DOMAIN>/canvas/ and setup.sh sets the system hostname to this,
# so each deployment can pick its own name (e.g. "canvas-zolder").
def _read_canvas_host() -> str:
    host = os.environ.get("CANVAS_HOST")
    if host:
        return host.strip()
    try:
        with open(os.path.join(_BASE_DIR, "canvas.conf")) as f:
            for line in f:
                line = line.strip()
                if line.startswith("CANVAS_HOST="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    except FileNotFoundError:
        pass
    return "canvas"


CANVAS_HOST = _read_canvas_host()
CANVAS_DOMAIN = f"{CANVAS_HOST}.local"

# Network/Discovery Constants
DEVICE_NAME = "HSG Canvas"
DEVICE_MANUFACTURER = "Hackerspace Gent"
APP_VERSION = "4.0.0-all-react"
CHROMECAST_CACHE_DURATION = 86400  # 24 hours
METADATA_UPDATE_INTERVAL = 15  # seconds

# Sendspin Protocol
# Listener port kept for status API (daemon uses 8928, display used 8929)
SENDSPIN_LISTENER_PORT = 8928


def _read_sendspin_name() -> str:
    """Name the sendspin player presents in Music Assistant, used to label its
    companion clients (e.g. the artwork display as "<name> - art").

    Resolution: SENDSPIN_NAME env, then the daemon's settings-daemon.json (the
    install-time source of truth set by setup.sh), then DEVICE_NAME.
    """
    name = os.environ.get("SENDSPIN_NAME")
    if name:
        return name.strip()
    try:
        with open(os.path.expanduser("~/.config/sendspin/settings-daemon.json")) as f:
            configured = json.load(f).get("name")
        if isinstance(configured, str) and configured.strip():
            return configured.strip()
    except (OSError, ValueError):
        pass
    return DEVICE_NAME


SENDSPIN_NAME = _read_sendspin_name()

# Server Configuration
DEFAULT_PORT = 8000
PRODUCTION_PORT = 8000
