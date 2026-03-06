"""
HSG Canvas Configuration

Central configuration file for all constants and settings.
"""
import os

# Base directory (for resolving relative paths)
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Paths
DEFAULT_BACKGROUND_PATH = os.path.join(_BASE_DIR, "canvas_background.png")

# Network/Discovery Constants
DEVICE_NAME = "HSG Canvas"
CHROMECAST_CACHE_DURATION = 86400  # 24 hours
METADATA_UPDATE_INTERVAL = 15  # seconds

# Server Configuration
DEFAULT_PORT = 8000
PRODUCTION_PORT = 8000
