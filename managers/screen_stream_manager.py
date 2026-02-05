"""
Screen Stream Manager

Handles screen capture streaming to SRS server.
"""
import asyncio
import logging
import os
import signal
import subprocess
from typing import Optional, Dict, Any

from config import SRS_RTMP_URL, SRS_HTTP_FLV_URL, SRS_HLS_URL
from utils.drm import get_optimal_connector_and_device as _get_optimal_connector_and_device


class ScreenStreamManager:
    """Manages screen capture streaming"""

    def __init__(self, display_detector):
        """
        Initialize Screen Stream Manager

        Args:
            display_detector: DisplayDetector for resolution detection
        """
        self.display_detector = display_detector
        self.screen_stream_process: Optional[subprocess.Popen] = None
        self.screen_stream_key: Optional[str] = None
        self.screen_stream_protocol: Optional[str] = None

    def get_optimal_connector_and_device(self) -> tuple[str, str]:
        """Get optimal DRM connector and device for current display"""
        return _get_optimal_connector_and_device(self.display_detector)

    async def start_screen_stream(self, stream_key: str, protocol: str = "rtmp") -> bool:
        """Start streaming the display output to SRS server"""
        try:
            # Stop existing screen stream if running
            if self.screen_stream_process:
                await self.stop_screen_stream()

            # Get current display resolution
            width, height, refresh = self.display_detector.get_resolution_for_content_type("stream")

            # Build target URL based on protocol
            if protocol == "rtmp":
                target_url = f"{SRS_RTMP_URL}/{stream_key}"
            elif protocol == "http_flv":
                target_url = f"{SRS_HTTP_FLV_URL}/{stream_key}.flv"
            elif protocol == "hls":
                target_url = f"{SRS_HLS_URL}/{stream_key}.m3u8"
            else:
                raise ValueError(f"Unsupported protocol: {protocol}")

            # Try different DRM-aware screen capture methods for headless Pi
            optimal_connector, optimal_device = self.get_optimal_connector_and_device()

            # Pi4 screen capture methods - prioritizing working methods
            capture_methods = []

            # Method 1: Framebuffer capture (WORKS - captures console/background but NOT DRM content like mpv videos)
            capture_methods.append([
                "ffmpeg", "-y", "-f", "fbdev", "-i", "/dev/fb0", "-r", "8",
                "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
                "-f", "flv", target_url
            ])

            # Method 2: FFmpeg kmsgrab (fails on Pi4 - requires universal planes capability)
            # This would capture DRM content if it worked, but Pi4 DRM driver doesn't support it
            capture_methods.append([
                "ffmpeg", "-y", "-f", "kmsgrab", "-i", "/dev/dri/card0", "-r", "5",
                "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
                "-f", "flv", target_url
            ])

            last_error = None
            for i, cmd in enumerate(capture_methods, 1):
                try:
                    method_names = [
                        "Framebuffer capture (/dev/fb0) - WORKS but only captures console/background",
                        "FFmpeg kmsgrab - FAILS on Pi4 (missing universal planes capability)"
                    ]
                    method_name = method_names[i-1] if i <= len(method_names) else f"Method {i}"
                    logging.info(f"Trying screen capture method {i}: {method_name}")

                    self.screen_stream_process = subprocess.Popen(
                        cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        preexec_fn=os.setsid
                    )

                    # Check if process starts successfully (shorter wait for faster methods like framebuffer)
                    await asyncio.sleep(0.5)
                    if self.screen_stream_process.poll() is None:
                        # Still running, success!
                        self.screen_stream_key = stream_key
                        self.screen_stream_protocol = protocol
                        logging.info(f"Screen streaming started: {stream_key} via {protocol} using {method_name}")
                        return True
                    else:
                        # Process died, get error
                        stdout, stderr = self.screen_stream_process.communicate()
                        error_output = stderr.decode() if stderr else stdout.decode()
                        last_error = f"{method_name}: {error_output[:500]}"
                        logging.warning(f"{method_name} failed: {error_output[:300]}")
                        self.screen_stream_process = None
                        continue

                except Exception as e:
                    last_error = f"{method_name}: {str(e)}"
                    logging.warning(f"{method_name} exception: {e}")
                    if self.screen_stream_process:
                        try:
                            self.screen_stream_process.terminate()
                        except:
                            pass
                        self.screen_stream_process = None
                    continue

            # All methods failed
            raise Exception(f"Screen capture failed. LIMITATION: Framebuffer capture only shows console/background, "
                          f"NOT DRM-rendered content (mpv videos, QR codes). kmsgrab requires universal planes capability "
                          f"not available in Pi4 DRM driver. For true DRM content capture, external tools or alternative "
                          f"approaches are needed. Last error: {last_error}")

        except Exception as e:
            logging.error(f"Failed to start screen stream: {e}")
            self.screen_stream_process = None
            self.screen_stream_key = None
            self.screen_stream_protocol = None
            return False

    async def stop_screen_stream(self) -> bool:
        """Stop screen streaming"""
        if not self.screen_stream_process:
            return False

        try:
            os.killpg(os.getpgid(self.screen_stream_process.pid), signal.SIGTERM)
            self.screen_stream_process.wait(timeout=5)
            stream_key = self.screen_stream_key
            protocol = self.screen_stream_protocol

            self.screen_stream_process = None
            self.screen_stream_key = None
            self.screen_stream_protocol = None

            logging.info(f"Screen streaming stopped: {stream_key} via {protocol}")
            return True
        except Exception as e:
            logging.error(f"Failed to stop screen stream: {e}")
            return False

    def is_screen_streaming(self) -> bool:
        """Check if screen streaming is currently active"""
        if not self.screen_stream_process:
            return False
        return self.screen_stream_process.poll() is None

    def get_screen_stream_info(self) -> Dict[str, Any]:
        """Get current screen stream information"""
        return {
            "active": self.is_screen_streaming(),
            "stream_key": self.screen_stream_key,
            "protocol": self.screen_stream_protocol,
            "pid": self.screen_stream_process.pid if self.screen_stream_process else None
        }
