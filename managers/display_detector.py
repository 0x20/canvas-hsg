"""
Display Capability Detector

Comprehensive display capability detection for optimal resolution utilization.
"""
import os
import logging
from typing import Tuple, List, Dict, Any


class DisplayCapabilityDetector:
    """Comprehensive display capability detection for optimal resolution utilization"""

    def __init__(self):
        self.capabilities = {}
        self.optimal_resolution = (640, 480)  # fallback
        self.optimal_refresh_rate = 60
        self.optimal_connector = "HDMI-A-1"
        self.available_resolutions = []
        self.detect_all_capabilities()

    def detect_all_capabilities(self):
        """Detect every possible display capability explicitly"""
        try:
            drm_path = "/sys/class/drm"
            best_resolution = (640, 480)
            best_refresh = 60
            best_connector = "HDMI-A-1"

            # Explicit resolution priority matrix
            resolution_priority = [
                (3840, 2160),  # 4K UHD
                (2560, 1440),  # 1440p
                (1920, 1200),  # WUXGA (1200p)
                (1920, 1080),  # 1080p
                (1680, 1050),  # WSXGA+
                (1600, 1200),  # UXGA
                (1440, 900),   # WXGA+
                (1366, 768),   # WXGA
                (1280, 1024),  # SXGA
                (1280, 720),   # 720p
                (1024, 768),   # XGA
                (800, 600),    # SVGA
                (640, 480)     # VGA fallback
            ]

            connectors_data = {}

            for item in os.listdir(drm_path):
                if item.startswith("card0-") or item.startswith("card1-"):
                    connector_path = os.path.join(drm_path, item, "status")
                    modes_path = os.path.join(drm_path, item, "modes")

                    if os.path.exists(connector_path) and os.path.exists(modes_path):
                        with open(connector_path, 'r') as f:
                            status = f.read().strip()

                        if status == "connected":
                            connector_name = item.replace("card0-", "").replace("card1-", "")

                            with open(modes_path, 'r') as f:
                                modes = f.readlines()

                            # Parse all available modes explicitly
                            available_modes = []
                            for mode_line in modes:
                                mode_line = mode_line.strip()
                                if 'x' in mode_line:
                                    try:
                                        # Parse resolution and refresh rate
                                        if '@' in mode_line:
                                            res_part, refresh_part = mode_line.split('@')
                                            refresh = float(refresh_part.replace('Hz', ''))
                                        else:
                                            res_part = mode_line
                                            refresh = 60  # default

                                        width, height = map(int, res_part.split('x'))
                                        available_modes.append((width, height, refresh))
                                    except:
                                        continue

                            connectors_data[connector_name] = {
                                'modes': available_modes,
                                'status': status,
                                'item': item
                            }

                            # Find highest priority resolution available
                            for priority_res in resolution_priority:
                                for width, height, refresh in available_modes:
                                    if (width, height) == priority_res:
                                        if (width * height) > (best_resolution[0] * best_resolution[1]):
                                            best_resolution = (width, height)
                                            best_refresh = refresh
                                            best_connector = connector_name
                                        break

            self.capabilities = connectors_data
            self.optimal_resolution = best_resolution
            self.optimal_refresh_rate = best_refresh
            self.optimal_connector = best_connector

            # Create explicit list of all available resolutions
            all_resolutions = set()
            for connector_data in connectors_data.values():
                for width, height, refresh in connector_data['modes']:
                    all_resolutions.add((width, height, refresh))

            self.available_resolutions = sorted(list(all_resolutions),
                                              key=lambda x: (x[0] * x[1], x[2]), reverse=True)

            logging.info(f"Display capabilities detected:")
            logging.info(f"  Optimal resolution: {best_resolution[0]}x{best_resolution[1]}@{best_refresh}Hz")
            logging.info(f"  Optimal connector: {best_connector}")
            logging.info(f"  Total available modes: {len(self.available_resolutions)}")

        except Exception as e:
            logging.error(f"Display capability detection failed: {e}")
            # Explicit fallback values
            self.optimal_resolution = (640, 480)
            self.optimal_refresh_rate = 60
            self.optimal_connector = "HDMI-A-1"
            self.available_resolutions = [(640, 480, 60)]

    async def initialize(self):
        """Async initialization (for compatibility with startup sequence)"""
        # Detection already done in __init__, this is for async compatibility
        pass

    @property
    def width(self) -> int:
        """Get optimal width"""
        return self.optimal_resolution[0]

    @property
    def height(self) -> int:
        """Get optimal height"""
        return self.optimal_resolution[1]

    @property
    def refresh_rate(self) -> float:
        """Get optimal refresh rate"""
        return self.optimal_refresh_rate

    def get_optimal_framebuffer_config(self) -> Dict[str, Any]:
        """Get optimal framebuffer configuration for detected capabilities"""
        return {
            'width': self.optimal_resolution[0],
            'height': self.optimal_resolution[1],
            'refresh_rate': self.optimal_refresh_rate,
            'connector': self.optimal_connector
        }

    def get_resolution_for_content_type(self, content_type: str) -> Tuple[int, int, float]:
        """Get optimal resolution for specific content type"""
        if content_type == "youtube":
            # Prefer common YouTube resolutions
            youtube_resolutions = [(3840, 2160), (1920, 1080), (1280, 720), (854, 480)]
            for yt_res in youtube_resolutions:
                for width, height, refresh in self.available_resolutions:
                    if (width, height) == yt_res:
                        return width, height, refresh

        # Default to optimal resolution
        return self.optimal_resolution[0], self.optimal_resolution[1], self.optimal_refresh_rate
