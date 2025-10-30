"""
Stream Manager

Handles stream republishing to SRS server using FFmpeg with GPU acceleration.
"""
import asyncio
import logging
import os
import signal
import subprocess
from datetime import datetime
from typing import Dict, Any, List

from config import SRS_RTMP_URL, SRS_HTTP_FLV_URL, SRS_HLS_URL


class StreamManager:
    """Manages stream republishing to SRS server"""

    def __init__(self):
        """Initialize Stream Manager"""
        self.active_streams: Dict[str, Dict[str, Any]] = {}

    async def start_stream(self, stream_key: str, source_url: str, protocol: str = "rtmp") -> bool:
        """Start publishing a stream using specified protocol with GPU acceleration"""
        try:
            if protocol == "rtmp":
                target_url = f"{SRS_RTMP_URL}/{stream_key}"
            elif protocol == "http_flv":
                target_url = f"{SRS_HTTP_FLV_URL}/{stream_key}.flv"
            elif protocol == "hls":
                target_url = f"{SRS_HLS_URL}/{stream_key}.m3u8"
            else:
                raise ValueError(f"Unsupported protocol: {protocol}")

            cmd = self._build_ffmpeg_cmd(source_url, target_url, protocol)

            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                preexec_fn=os.setsid
            )

            self.active_streams[stream_key] = {
                "process": process,
                "source_url": source_url,
                "protocol": protocol,
                "target_url": target_url,
                "started_at": datetime.now().isoformat(),
                "status": "active"
            }

            logging.info(f"Started GPU-accelerated stream {stream_key} via {protocol}")
            return True
        except Exception as e:
            logging.error(f"Failed to start stream {stream_key} with {protocol}: {e}")
            return False

    def _build_ffmpeg_cmd(self, source_url: str, target_url: str, protocol: str) -> List[str]:
        """Build optimized ffmpeg command with Pi4 GPU acceleration"""
        base_cmd = [
            "ffmpeg", "-re",
            "-hwaccel", "v4l2m2m",  # Pi4 hardware acceleration
            "-hwaccel_output_format", "drm_prime",
            "-i", source_url
        ]

        if protocol == "rtmp":
            return base_cmd + [
                # Video encoding with Pi4 GPU
                "-c:v", "h264_v4l2m2m",
                "-b:v", "4M",  # Higher bitrate for Pi4
                "-maxrate", "4.5M", "-bufsize", "8M",
                "-profile:v", "high", "-level:v", "4.1",
                "-keyint_min", "30", "-g", "60", "-sc_threshold", "0",
                "-preset", "fast",
                # Audio encoding
                "-c:a", "aac", "-b:a", "256k", "-ar", "48000",
                # Output format
                "-f", "flv", target_url
            ]
        else:
            return base_cmd + [
                "-c:v", "h264_v4l2m2m", "-b:v", "3M",
                "-c:a", "aac", "-b:a", "192k",
                "-f", "flv", target_url
            ]

    async def stop_stream(self, stream_key: str) -> bool:
        """Stop a specific stream"""
        if stream_key not in self.active_streams:
            return False

        try:
            process = self.active_streams[stream_key]["process"]
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
            process.wait(timeout=5)
            del self.active_streams[stream_key]
            logging.info(f"Stopped stream {stream_key}")
            return True
        except Exception as e:
            logging.error(f"Failed to stop stream {stream_key}: {e}")
            return False

    def get_active_streams(self) -> Dict[str, Dict[str, Any]]:
        """Get information about all active streams"""
        stream_info = {}
        for key, stream in self.active_streams.items():
            stream_info[key] = {
                "source_url": stream["source_url"],
                "protocol": stream["protocol"],
                "target_url": stream["target_url"],
                "started_at": stream["started_at"],
                "status": "active" if stream["process"].poll() is None else "stopped",
                "pid": stream["process"].pid
            }
        return stream_info

    async def cleanup(self):
        """Stop all active streams"""
        for stream_key in list(self.active_streams.keys()):
            await self.stop_stream(stream_key)
