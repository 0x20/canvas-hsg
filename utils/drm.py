"""
Shared DRM connector detection utilities.

Used by PlaybackManager and ScreenStreamManager.
"""
import logging
from typing import Tuple


def get_optimal_connector_and_device(display_detector) -> Tuple[str, str]:
    """
    Get optimal DRM connector and device for the current display.

    Args:
        display_detector: DisplayCapabilityDetector instance

    Returns:
        Tuple of (connector_name, device_path), e.g. ("HDMI-A-1", "/dev/dri/card0")
    """
    try:
        connector = display_detector.optimal_connector

        # Determine DRM device based on connector
        if connector in display_detector.capabilities:
            connector_data = display_detector.capabilities[connector]
            if connector_data['item'].startswith('card1-'):
                return connector, '/dev/dri/card1'
            else:
                return connector, '/dev/dri/card0'

        return "HDMI-A-1", "/dev/dri/card0"

    except Exception as e:
        logging.warning(f"Failed to get optimal connector: {e}")
        return "HDMI-A-1", "/dev/dri/card0"
