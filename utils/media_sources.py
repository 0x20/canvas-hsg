"""Loader for media_sources.yaml (radio stations and YouTube presets)."""
import logging
import os
from typing import Any, Dict

import yaml

MEDIA_SOURCES_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "media_sources.yaml"
)


def load_media_sources() -> Dict[str, Any]:
    """The parsed file, or empty groups when it is missing or invalid."""
    try:
        with open(MEDIA_SOURCES_PATH, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        logging.warning(f"Media sources config not found at {MEDIA_SOURCES_PATH}")
    except Exception as e:
        logging.error(f"Error loading media sources: {e}")
    return {"music_streams": {}, "youtube_channels": {}}
