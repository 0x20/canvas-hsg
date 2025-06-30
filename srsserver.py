"""
HSG Canvas (Hackerspace.gent Canvas) - DRM/GPU Optimized for Pi4
A FastAPI-based server for controlling media streams and playback on Raspberry Pi.
Optimized for maximum performance using DRM/KMS acceleration.
"""

import asyncio
import subprocess
import json
import logging
import os
import signal
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional, Dict, Any, List
from pathlib import Path
import base64

import uvicorn
import requests
import psutil
from fastapi import FastAPI, HTTPException, BackgroundTasks, Request, File, UploadFile
from fastapi.responses import JSONResponse, HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from PIL import Image, ImageDraw, ImageFont
import numpy as np
import mmap
import qrcode
import io

# Configuration
HOST="localhost"
SRS_RTMP_URL = f"rtmp://{HOST}:1935/live"
SRS_HTTP_FLV_URL = f"http://{HOST}:8080/live"
SRS_HLS_URL = f"http://{HOST}:8080/live"
SRS_API_URL = f"http://{HOST}:1985/api/v1"
DEFAULT_BACKGROUND_PATH = "/tmp/stream_images/default_background.jpg"

# Explicit player command matrix for all resolutions
OPTIMAL_PLAYER_COMMANDS = {
    # 4K UHD Commands
    "mpv_3840x2160_60hz": [
        "mpv", "--vo=drm", "--drm-mode=3840x2160@60", "--fs", "--quiet",
        "--no-input-default-bindings", "--no-osc", "--hwdec=v4l2m2m",
        "--vd-lavc-threads=4", "--cache=yes", "--demuxer-max-bytes=150MiB"
    ],
    "mpv_3840x2160_30hz": [
        "mpv", "--vo=drm", "--drm-mode=3840x2160@30", "--fs", "--quiet",
        "--no-input-default-bindings", "--no-osc", "--hwdec=v4l2m2m"
    ],
    
    # 1440p Commands
    "mpv_2560x1440_144hz": [
        "mpv", "--vo=drm", "--drm-mode=2560x1440@144", "--fs", "--quiet",
        "--no-input-default-bindings", "--no-osc", "--hwdec=v4l2m2m",
        "--interpolation", "--video-sync=display-resample"
    ],
    "mpv_2560x1440_120hz": [
        "mpv", "--vo=drm", "--drm-mode=2560x1440@120", "--fs", "--quiet",
        "--no-input-default-bindings", "--no-osc", "--hwdec=v4l2m2m"
    ],
    "mpv_2560x1440_60hz": [
        "mpv", "--vo=drm", "--drm-mode=2560x1440@60", "--fs", "--quiet",
        "--no-input-default-bindings", "--no-osc", "--hwdec=v4l2m2m"
    ],
    
    # 1080p Commands
    "mpv_1920x1080_144hz": [
        "mpv", "--vo=drm", "--drm-mode=1920x1080@144", "--fs", "--quiet",
        "--no-input-default-bindings", "--no-osc", "--hwdec=v4l2m2m",
        "--interpolation", "--video-sync=display-resample"
    ],
    "mpv_1920x1080_120hz": [
        "mpv", "--vo=drm", "--drm-mode=1920x1080@120", "--fs", "--quiet",
        "--no-input-default-bindings", "--no-osc", "--hwdec=v4l2m2m"
    ],
    "mpv_1920x1080_60hz": [
        "mpv", "--vo=drm", "--drm-mode=1920x1080@60", "--fs", "--quiet",
        "--no-input-default-bindings", "--no-osc", "--hwdec=v4l2m2m"
    ],
    
    # 720p Commands
    "mpv_1280x720_120hz": [
        "mpv", "--vo=drm", "--drm-mode=1280x720@120", "--fs", "--quiet",
        "--no-input-default-bindings", "--no-osc", "--hwdec=v4l2m2m"
    ],
    "mpv_1280x720_60hz": [
        "mpv", "--vo=drm", "--drm-mode=1280x720@60", "--fs", "--quiet",
        "--no-input-default-bindings", "--no-osc", "--hwdec=v4l2m2m"
    ],
    
    # XGA Commands
    "mpv_1024x768_75hz": [
        "mpv", "--vo=drm", "--drm-mode=1024x768@75", "--fs", "--quiet",
        "--no-input-default-bindings", "--no-osc", "--hwdec=v4l2m2m"
    ],
    "mpv_1024x768_60hz": [
        "mpv", "--vo=drm", "--drm-mode=1024x768@60", "--fs", "--quiet",
        "--no-input-default-bindings", "--no-osc", "--hwdec=v4l2m2m"
    ],
    
    # SVGA Commands
    "mpv_800x600_75hz": [
        "mpv", "--vo=drm", "--drm-mode=800x600@75", "--fs", "--quiet",
        "--no-input-default-bindings", "--no-osc", "--hwdec=v4l2m2m"
    ],
    "mpv_800x600_60hz": [
        "mpv", "--vo=drm", "--drm-mode=800x600@60", "--fs", "--quiet",
        "--no-input-default-bindings", "--no-osc", "--hwdec=v4l2m2m"
    ],
    
    # VGA Fallback Commands
    "mpv_640x480_60hz": [
        "mpv", "--vo=drm", "--drm-mode=640x480@60", "--fs", "--quiet",
        "--no-input-default-bindings", "--no-osc"
    ],
    
    # FFplay Variants
    "ffplay_3840x2160_60hz": [
        "ffplay", "-fs", "-autoexit", "-hwaccel", "v4l2m2m",
        "-video_size", "3840x2160", "-framerate", "60"
    ],
    "ffplay_1920x1080_60hz": [
        "ffplay", "-fs", "-autoexit", "-hwaccel", "v4l2m2m",
        "-video_size", "1920x1080", "-framerate", "60"
    ],
    "ffplay_1024x768_60hz": [
        "ffplay", "-fs", "-autoexit", "-hwaccel", "v4l2m2m",
        "-video_size", "1024x768", "-framerate", "60"
    ],
    
    # VLC Variants
    "vlc_3840x2160_60hz": [
        "vlc", "--intf", "dummy", "--fullscreen", "--avcodec-hw", "v4l2m2m",
        "--width", "3840", "--height", "2160"
    ],
    "vlc_1920x1080_60hz": [
        "vlc", "--intf", "dummy", "--fullscreen", "--avcodec-hw", "v4l2m2m",
        "--width", "1920", "--height", "1080"
    ],
    "vlc_1024x768_60hz": [
        "vlc", "--intf", "dummy", "--fullscreen", "--avcodec-hw", "v4l2m2m",
        "--width", "1024", "--height", "768"
    ],
    
    # Legacy compatibility commands
    "mpv_basic": ["mpv", "--vo=drm", "--fs", "--quiet"],
    "mpv_optimized": [
        "mpv", "--vo=drm", "--fs", "--quiet", 
        "--no-input-default-bindings", "--no-osc", "--untimed"
    ],
    "ffplay_basic": ["ffplay", "-fs", "-autoexit"],
    "vlc_basic": ["vlc", "--intf", "dummy", "--fullscreen"]
}

# Legacy player commands for backward compatibility
PLAYER_COMMANDS = {
    "mpv": {
        "basic": OPTIMAL_PLAYER_COMMANDS["mpv_basic"],
        "optimized": OPTIMAL_PLAYER_COMMANDS["mpv_optimized"],
        "fullscreen": OPTIMAL_PLAYER_COMMANDS["mpv_optimized"],
        "drm": OPTIMAL_PLAYER_COMMANDS["mpv_optimized"],
        "auto_mode": OPTIMAL_PLAYER_COMMANDS["mpv_optimized"],
        "1024x768": OPTIMAL_PLAYER_COMMANDS["mpv_1024x768_60hz"],
        "800x600": OPTIMAL_PLAYER_COMMANDS["mpv_800x600_60hz"]
    },
    "ffplay": {
        "basic": OPTIMAL_PLAYER_COMMANDS["ffplay_basic"],
        "optimized": OPTIMAL_PLAYER_COMMANDS["ffplay_1024x768_60hz"],
        "fullscreen": OPTIMAL_PLAYER_COMMANDS["ffplay_1024x768_60hz"]
    },
    "vlc": {
        "basic": OPTIMAL_PLAYER_COMMANDS["vlc_basic"],
        "optimized": OPTIMAL_PLAYER_COMMANDS["vlc_1024x768_60hz"],
        "fullscreen": OPTIMAL_PLAYER_COMMANDS["vlc_1024x768_60hz"]
    }
}

# Pydantic models for API
class StreamStartRequest(BaseModel):
    source_url: str
    protocol: str = "rtmp"

class PlaybackStartRequest(BaseModel):
    player: str = "mpv"
    mode: str = "optimized" 
    protocol: str = "rtmp"

class ImageDisplayRequest(BaseModel):
    image_data: str  # base64 encoded image
    duration: int = 10  # seconds to display

class YoutubePlayRequest(BaseModel):
    youtube_url: str
    duration: Optional[int] = None  # None = play full video

class QRCodeRequest(BaseModel):
    content: str  # URL or text to encode in QR code
    duration: Optional[int] = None  # seconds to display, None = forever

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
    
    def get_optimal_framebuffer_config(self):
        """Get optimal framebuffer configuration for detected capabilities"""
        return {
            'width': self.optimal_resolution[0],
            'height': self.optimal_resolution[1],
            'refresh_rate': self.optimal_refresh_rate,
            'connector': self.optimal_connector
        }
    
    def get_resolution_for_content_type(self, content_type: str):
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

class FramebufferManager:
    """Direct framebuffer management for seamless background display with optimal resolution"""
    
    def __init__(self, display_detector: DisplayCapabilityDetector):
        self.display_detector = display_detector
        self.fb_device = "/dev/fb0"
        
        # Get optimal configuration from display detector
        optimal_config = display_detector.get_optimal_framebuffer_config()
        self.target_width = optimal_config['width']
        self.target_height = optimal_config['height']
        
        # Actual framebuffer parameters (may differ from target)
        self.fb_width = 640  # will be updated by _get_fb_info
        self.fb_height = 480  # will be updated by _get_fb_info
        self.fb_bpp = 16  # bits per pixel
        self.fb_bytes_per_pixel = self.fb_bpp // 8
        self.fb_size = self.fb_width * self.fb_height * self.fb_bytes_per_pixel
        self.fb_format = 'RGB565'  # 5 bits red, 6 bits green, 5 bits blue
        
        # Memory management
        self.fb_file = None
        self.fb_mmap = None
        self.fb_array = None
        self.is_available = False
        
        # Performance optimization - pre-calculate scaling parameters
        self.scale_x = 1.0
        self.scale_y = 1.0
        
        self._initialize_framebuffer()
    
    def _initialize_framebuffer(self):
        """Initialize framebuffer access and memory mapping with optimal resolution awareness"""
        try:
            # Get actual framebuffer info
            self._get_fb_info()
            
            # Calculate scaling parameters for optimal resolution rendering
            self.scale_x = self.fb_width / self.target_width
            self.scale_y = self.fb_height / self.target_height
            
            # Open framebuffer device
            self.fb_file = open(self.fb_device, 'r+b')
            
            # Create memory map
            self.fb_mmap = mmap.mmap(self.fb_file.fileno(), self.fb_size)
            
            # Create numpy array view of framebuffer
            if self.fb_bpp == 16:
                self.fb_array = np.frombuffer(self.fb_mmap, dtype=np.uint16).reshape((self.fb_height, self.fb_width))
            else:
                self.fb_array = np.frombuffer(self.fb_mmap, dtype=np.uint32).reshape((self.fb_height, self.fb_width))
            
            self.is_available = True
            logging.info(f"Framebuffer initialized: {self.fb_width}x{self.fb_height}, {self.fb_bpp}bpp")
            logging.info(f"Target resolution: {self.target_width}x{self.target_height}")
            logging.info(f"Scaling factors: {self.scale_x:.3f}x, {self.scale_y:.3f}y")
            
        except Exception as e:
            logging.warning(f"Framebuffer not available: {e}")
            self.is_available = False
    
    def _get_fb_info(self):
        """Get framebuffer information from system"""
        try:
            # Read virtual size
            with open('/sys/class/graphics/fb0/virtual_size', 'r') as f:
                size_str = f.read().strip()
                self.fb_width, self.fb_height = map(int, size_str.split(','))
            
            # Read bits per pixel
            with open('/sys/class/graphics/fb0/bits_per_pixel', 'r') as f:
                self.fb_bpp = int(f.read().strip())
            
            self.fb_bytes_per_pixel = self.fb_bpp // 8
            self.fb_size = self.fb_width * self.fb_height * self.fb_bytes_per_pixel
            
        except Exception as e:
            logging.warning(f"Could not read framebuffer info, using defaults: {e}")
    
    def _rgb_to_rgb565(self, r, g, b):
        """Convert RGB888 to RGB565 format"""
        # Convert 8-bit values to appropriate bit ranges
        r5 = (r >> 3) & 0x1F  # 5 bits
        g6 = (g >> 2) & 0x3F  # 6 bits  
        b5 = (b >> 3) & 0x1F  # 5 bits
        
        # Pack into 16-bit value: RRRRRGGGGGGBBBBB
        return (r5 << 11) | (g6 << 5) | b5
    
    def display_image(self, image_path: str) -> bool:
        """Display an image on the framebuffer"""
        if not self.is_available:
            return False
            
        try:
            # Load and resize image
            with Image.open(image_path) as img:
                # Convert to RGB if needed
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                
                # Resize to framebuffer dimensions
                img_resized = img.resize((self.fb_width, self.fb_height), Image.Resampling.LANCZOS)
                
                # Convert to numpy array
                img_array = np.array(img_resized)
                
                # Convert to framebuffer format using vectorized operations
                if self.fb_bpp == 16:
                    # Convert RGB888 to RGB565 efficiently
                    r = (img_array[:, :, 0] >> 3).astype(np.uint16)
                    g = (img_array[:, :, 1] >> 2).astype(np.uint16)
                    b = (img_array[:, :, 2] >> 3).astype(np.uint16)
                    fb_data = (r << 11) | (g << 5) | b
                else:
                    # Assume 32-bit RGBA
                    r = img_array[:, :, 0].astype(np.uint32)
                    g = img_array[:, :, 1].astype(np.uint32)
                    b = img_array[:, :, 2].astype(np.uint32)
                    fb_data = (0xFF << 24) | (r << 16) | (g << 8) | b
                
                # Write to framebuffer
                np.copyto(self.fb_array, fb_data)
                self.fb_mmap.flush()
                
                logging.info(f"Successfully displayed image on framebuffer: {image_path}")
                return True
                
        except Exception as e:
            logging.error(f"Failed to display image on framebuffer: {e}")
            return False
    
    def clear_screen(self, color=(0, 0, 0)):
        """Clear framebuffer to solid color"""
        if not self.is_available:
            return False
            
        try:
            if self.fb_bpp == 16:
                color_value = self._rgb_to_rgb565(color[0], color[1], color[2])
            else:
                color_value = (0xFF << 24) | (color[0] << 16) | (color[1] << 8) | color[2]
            
            self.fb_array.fill(color_value)
            self.fb_mmap.flush()
            return True
            
        except Exception as e:
            logging.error(f"Failed to clear framebuffer: {e}")
            return False
    
    def cleanup(self):
        """Clean up framebuffer resources"""
        try:
            if self.fb_mmap:
                self.fb_mmap.close()
            if self.fb_file:
                self.fb_file.close()
        except Exception as e:
            logging.error(f"Error cleaning up framebuffer: {e}")

class HDMICECManager:
    """Manages HDMI-CEC functionality for TV/monitor power control"""
    
    def __init__(self):
        self.is_available = False
        self.cec_devices = []
        self.tv_address = "0"  # Default TV address
        self.cec_adapter = None
        self.command_timeout = 10  # seconds
        
        # Check CEC availability
        self._detect_cec_support()
        
    def _detect_cec_support(self) -> None:
        """Detect HDMI-CEC support and available devices"""
        try:
            # Check for CEC device files
            cec_devices = ["/dev/cec0", "/dev/cec1"]
            available_devices = []
            
            for device in cec_devices:
                if os.path.exists(device):
                    try:
                        # Test read access
                        with open(device, 'r'):
                            available_devices.append(device)
                    except PermissionError:
                        logging.warning(f"CEC device {device} exists but no permission")
                    except Exception:
                        pass  # Device exists but not accessible
            
            # Check for cec-client availability
            try:
                result = subprocess.run(["which", "cec-client"], 
                                      capture_output=True, text=True, timeout=5)
                cec_client_available = result.returncode == 0
            except Exception:
                cec_client_available = False
            
            if available_devices and cec_client_available:
                self.is_available = True
                self.cec_adapter = available_devices[0]  # Use first available
                logging.info(f"HDMI-CEC available: adapter={self.cec_adapter}")
                
                # Skip initial scan to avoid blocking startup - scan will happen on first API call
            else:
                reasons = []
                if not available_devices:
                    reasons.append("no CEC devices found")
                if not cec_client_available:
                    reasons.append("cec-client not installed")
                logging.warning(f"HDMI-CEC not available: {', '.join(reasons)}")
                
        except Exception as e:
            logging.error(f"Error detecting CEC support: {e}")
    
    def _scan_cec_devices(self) -> None:
        """Scan for connected CEC devices"""
        try:
            cmd = ["cec-client", "-s", "-d", "1"]
            process = subprocess.Popen(cmd, stdin=subprocess.PIPE, 
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, 
                                     text=True)
            
            stdout, stderr = process.communicate(input="scan\nq\n", timeout=self.command_timeout)
            
            if process.returncode == 0:
                # Parse scan results to find connected devices
                devices = []
                for line in stdout.split('\n'):
                    if 'device #' in line.lower() and 'tv' in line.lower():
                        # Found TV device, extract address
                        if '(' in line and ')' in line:
                            addr_part = line[line.find('(') + 1:line.find(')')]
                            if addr_part:
                                self.tv_address = addr_part.split('.')[0]  # Get first part
                        devices.append(line.strip())
                
                self.cec_devices = devices
                logging.info(f"CEC scan found {len(devices)} devices, TV address: {self.tv_address}")
            else:
                logging.warning(f"CEC scan failed: {stderr}")
                
        except subprocess.TimeoutExpired:
            logging.error("CEC scan timed out")
        except Exception as e:
            logging.error(f"Error scanning CEC devices: {e}")
    
    def _execute_cec_command(self, command: str) -> tuple[bool, str]:
        """Execute a CEC command with timeout and error handling"""
        if not self.is_available:
            return False, "HDMI-CEC not available"
        
        try:
            cmd = ["cec-client", "-s", "-d", "1"]
            process = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                     text=True)
            
            input_cmd = f"{command}\nq\n"
            stdout, stderr = process.communicate(input=input_cmd, timeout=self.command_timeout)
            
            success = process.returncode == 0
            output = stdout if success else stderr
            
            return success, output.strip()
            
        except subprocess.TimeoutExpired:
            return False, "Command timed out"
        except Exception as e:
            return False, f"Command failed: {str(e)}"
    
    async def power_on_tv(self) -> dict:
        """Turn on the TV via HDMI-CEC"""
        success, output = self._execute_cec_command(f"on {self.tv_address}")
        
        return {
            "success": success,
            "message": "TV power on command sent" if success else f"Failed to power on TV: {output}",
            "output": output,
            "tv_address": self.tv_address
        }
    
    async def power_off_tv(self) -> dict:
        """Put TV in standby via HDMI-CEC"""
        success, output = self._execute_cec_command(f"standby {self.tv_address}")
        
        return {
            "success": success,
            "message": "TV standby command sent" if success else f"Failed to put TV in standby: {output}",
            "output": output,
            "tv_address": self.tv_address
        }
    
    async def get_tv_power_status(self) -> dict:
        """Check TV power status via HDMI-CEC"""
        success, output = self._execute_cec_command(f"pow {self.tv_address}")
        
        # Parse power status from output
        power_status = "unknown"
        if success and output:
            if "on" in output.lower():
                power_status = "on"
            elif "standby" in output.lower() or "off" in output.lower():
                power_status = "standby"
        
        return {
            "success": success,
            "power_status": power_status,
            "output": output,
            "tv_address": self.tv_address
        }
    
    async def scan_devices(self) -> dict:
        """Scan for CEC devices and return results"""
        self._scan_cec_devices()
        
        return {
            "success": self.is_available,
            "devices": self.cec_devices,
            "tv_address": self.tv_address,
            "adapter": self.cec_adapter
        }
    
    def get_status(self) -> dict:
        """Get comprehensive CEC status information"""
        return {
            "available": self.is_available,
            "adapter": self.cec_adapter,
            "tv_address": self.tv_address,
            "devices_found": len(self.cec_devices),
            "devices": self.cec_devices,
            "command_timeout": self.command_timeout
        }

class StreamManager:
    """Manages streaming and playback processes with DRM optimization"""
    
    def __init__(self):
        self.active_streams: Dict[str, Dict[str, Any]] = {}
        self.player_process: Optional[subprocess.Popen] = None
        self.current_stream: Optional[str] = None
        self.current_protocol: Optional[str] = None
        self.current_player: Optional[str] = None
        self.background_process: Optional[subprocess.Popen] = None
        
        # Background mode management
        from background_modes import BackgroundManager
        self.background_manager = None  # Will be initialized after framebuffer
        
        # Screen streaming state
        self.screen_stream_process: Optional[subprocess.Popen] = None
        self.screen_stream_key: Optional[str] = None
        self.screen_stream_protocol: Optional[str] = None
        
        # Initialize display capability detection first
        self.display_detector = DisplayCapabilityDetector()
        
        # Legacy DRM detection for backward compatibility
        self.drm_connector = self.display_detector.optimal_connector
        self.gpu_memory = self._get_gpu_memory()
        
        # Initialize framebuffer manager with optimal resolution support
        self.framebuffer = FramebufferManager(self.display_detector)
        if self.framebuffer.is_available:
            logging.info("Optimal resolution framebuffer background manager initialized")
        else:
            logging.warning("Framebuffer not available, will use fallback methods")
        
        # Initialize background manager
        self.background_manager = BackgroundManager(self.display_detector, self.framebuffer)
        
        # Initialize HDMI-CEC manager
        self.cec_manager = HDMICECManager()
        
    def _detect_drm_connector(self) -> str:
        """Detect the active DRM connector for Pi4 and check available modes"""
        try:
            # Check for HDMI connectors
            drm_path = "/sys/class/drm"
            connectors = []
            best_connector = None
            max_modes = 0
            
            for item in os.listdir(drm_path):
                if item.startswith("card0-"):
                    connector_path = os.path.join(drm_path, item, "status")
                    modes_path = os.path.join(drm_path, item, "modes")
                    
                    if os.path.exists(connector_path):
                        with open(connector_path, 'r') as f:
                            status = f.read().strip()
                        
                        connector_name = item.replace("card0-", "")
                        
                        if status == "connected":
                            connectors.append(connector_name)
                            
                            # Check how many modes this connector supports
                            if os.path.exists(modes_path):
                                try:
                                    with open(modes_path, 'r') as f:
                                        modes = f.readlines()
                                    
                                    # Log available modes for debugging
                                    logging.info(f"Connector {connector_name} has {len(modes)} modes:")
                                    for mode in modes[:5]:  # Log first 5 modes
                                        logging.info(f"  {mode.strip()}")
                                    if len(modes) > 5:
                                        logging.info(f"  ... and {len(modes) - 5} more modes")
                                    
                                    # Check if this connector has 1920x1080
                                    has_1080p = any('1920x1080' in mode for mode in modes)
                                    if has_1080p:
                                        logging.info(f"Connector {connector_name} supports 1920x1080!")
                                        best_connector = connector_name
                                        break
                                    
                                    # Keep track of connector with most modes
                                    if len(modes) > max_modes:
                                        max_modes = len(modes)
                                        best_connector = connector_name
                                        
                                except Exception as e:
                                    logging.warning(f"Could not read modes for {connector_name}: {e}")
            
            # Use the best connector found
            if best_connector:
                logging.info(f"Using DRM connector: {best_connector} (best available)")
                return best_connector
            elif connectors:
                logging.info(f"Using DRM connector: {connectors[0]} (first connected)")
                return connectors[0]
                
            logging.warning("No connected DRM connector found, using HDMI-A-1 as default")
            return "HDMI-A-1"
            
        except Exception as e:
            logging.error(f"Failed to detect DRM connector: {e}")
            return "HDMI-A-1"
    
    def _get_gpu_memory(self) -> int:
        """Get GPU memory split for Pi4"""
        try:
            result = subprocess.run(['vcgencmd', 'get_mem', 'gpu'], 
                                  capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                gpu_mem = int(result.stdout.strip().replace('gpu=', '').replace('M', ''))
                logging.info(f"GPU memory: {gpu_mem}MB")
                return gpu_mem
        except Exception as e:
            logging.error(f"Failed to get GPU memory: {e}")
        return 128  # Default assumption
    
    def get_optimal_player_command(self, player: str, content_type: str = "stream") -> List[str]:
        """Get optimal player command based on display capabilities"""
        try:
            # Get resolution for content type
            width, height, refresh = self.display_detector.get_resolution_for_content_type(content_type)
            
            # Create command key based on resolution and refresh rate
            command_key = f"{player}_{width}x{height}_{int(refresh)}hz"
            
            # Try exact match first
            if command_key in OPTIMAL_PLAYER_COMMANDS:
                return OPTIMAL_PLAYER_COMMANDS[command_key].copy()
            
            # Try without refresh rate
            command_key_no_refresh = f"{player}_{width}x{height}_60hz"
            if command_key_no_refresh in OPTIMAL_PLAYER_COMMANDS:
                return OPTIMAL_PLAYER_COMMANDS[command_key_no_refresh].copy()
            
            # Fall back to common resolutions for this player
            fallback_resolutions = [
                (3840, 2160), (2560, 1440), (1920, 1080), 
                (1280, 720), (1024, 768), (800, 600), (640, 480)
            ]
            
            for fallback_width, fallback_height in fallback_resolutions:
                if (fallback_width, fallback_height, 60) in self.display_detector.available_resolutions:
                    fallback_key = f"{player}_{fallback_width}x{fallback_height}_60hz"
                    if fallback_key in OPTIMAL_PLAYER_COMMANDS:
                        logging.info(f"Using fallback player command: {fallback_key}")
                        return OPTIMAL_PLAYER_COMMANDS[fallback_key].copy()
            
            # Ultimate fallback to basic command
            basic_key = f"{player}_basic"
            if basic_key in OPTIMAL_PLAYER_COMMANDS:
                logging.warning(f"Using basic player command for {player}")
                return OPTIMAL_PLAYER_COMMANDS[basic_key].copy()
            
            # Legacy fallback
            if player in PLAYER_COMMANDS and "optimized" in PLAYER_COMMANDS[player]:
                logging.warning(f"Using legacy player command for {player}")
                return PLAYER_COMMANDS[player]["optimized"].copy()
            
            # Final fallback
            return ["mpv", "--vo=drm", "--fs", "--quiet"]
            
        except Exception as e:
            logging.error(f"Failed to get optimal player command: {e}")
            return ["mpv", "--vo=drm", "--fs", "--quiet"]
    
    def get_optimal_connector_and_device(self) -> tuple[str, str]:
        """Get optimal DRM connector and device for current display"""
        try:
            connector = self.display_detector.optimal_connector
            
            # Determine DRM device based on connector
            if connector in self.display_detector.capabilities:
                connector_data = self.display_detector.capabilities[connector]
                if connector_data['item'].startswith('card1-'):
                    return connector, '/dev/dri/card1'
                else:
                    return connector, '/dev/dri/card0'
            
            return "HDMI-A-1", "/dev/dri/card0"
            
        except Exception as e:
            logging.error(f"Failed to get optimal connector: {e}")
            return "HDMI-A-1", "/dev/dri/card0"
        
    async def create_default_background(self, mode: str = "static"):
        """Create and display background using the new background manager"""
        try:
            from background_modes import BackgroundMode
            
            # Convert mode string to enum
            if mode == "splitflap_clock":
                bg_mode = BackgroundMode.SPLITFLAP_CLOCK
            else:
                bg_mode = BackgroundMode.STATIC
            
            # Set background mode
            success = await self.background_manager.set_mode(bg_mode)
            if success:
                logging.info(f"Background set to {mode} mode")
            else:
                logging.error(f"Failed to set background to {mode} mode")
                
        except Exception as e:
            logging.error(f"Failed to create background: {e}")
    
    async def set_background_mode(self, mode: str) -> bool:
        """Set background mode (static or splitflap_clock)"""
        return await self.create_default_background(mode)
    
    def get_background_status(self) -> dict:
        """Get current background status"""
        if self.background_manager:
            return self.background_manager.get_status()
        return {"mode": "unknown", "is_running": False}
        
    async def start_stream(self, stream_key: str, source_url: str, protocol: str = "rtmp") -> bool:
        """Start publishing a stream using specified protocol with GPU acceleration"""
        try:
            if protocol == "rtmp":
                target_url = f"{SRS_RTMP_URL}/{stream_key}"
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
            raise Exception(f"Screen capture failed. LIMITATION: Framebuffer capture only shows console/background, NOT DRM-rendered content (mpv videos, QR codes). kmsgrab requires universal planes capability not available in Pi4 DRM driver. For true DRM content capture, external tools or alternative approaches are needed. Last error: {last_error}")
            
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
            "protocol": self.screen_stream_protocol
        }
    
    def check_screen_capture_capabilities(self) -> Dict[str, Any]:
        """Check FFmpeg and DRM capabilities for screen capture"""
        capabilities = {
            "ffmpeg_version": None,
            "kmsgrab_available": False,
            "fbdev_available": False,
            "drm_devices": [],
            "drm_permissions": {},
            "user_groups": [],
            "recommendations": []
        }
        
        try:
            # Check FFmpeg version and formats
            result = subprocess.run(['ffmpeg', '-version'], capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                lines = result.stdout.split('\n')
                capabilities["ffmpeg_version"] = lines[0] if lines else "Unknown"
            
            # Check available input formats
            result = subprocess.run(['ffmpeg', '-formats'], capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                formats_output = result.stdout
                capabilities["kmsgrab_available"] = 'kmsgrab' in formats_output
                capabilities["fbdev_available"] = 'fbdev' in formats_output
                
        except Exception as e:
            capabilities["ffmpeg_error"] = str(e)
        
        try:
            # Check DRM devices
            drm_path = "/dev/dri"
            if os.path.exists(drm_path):
                for device in os.listdir(drm_path):
                    device_path = f"{drm_path}/{device}"
                    capabilities["drm_devices"].append(device)
                    capabilities["drm_permissions"][device] = {
                        "readable": os.access(device_path, os.R_OK),
                        "writable": os.access(device_path, os.W_OK),
                        "path": device_path
                    }
        except Exception as e:
            capabilities["drm_error"] = str(e)
        
        try:
            # Check user groups
            import grp
            user_groups = [g.gr_name for g in grp.getgrall() if os.getenv('USER', 'root') in g.gr_mem]
            capabilities["user_groups"] = user_groups
        except Exception:
            capabilities["user_groups"] = ["unknown"]
        
        # Generate recommendations
        recommendations = []
        
        if not capabilities["kmsgrab_available"]:
            recommendations.append("FFmpeg lacks kmsgrab support. Install FFmpeg with DRM support: sudo apt install libdrm-dev")
        
        if not any(perms["readable"] and perms["writable"] for perms in capabilities["drm_permissions"].values()):
            recommendations.append("No DRM device access. Add user to groups: sudo usermod -a -G video,render $USER")
        
        if "video" not in capabilities["user_groups"]:
            recommendations.append("User not in video group: sudo usermod -a -G video $USER")
            
        if "render" not in capabilities["user_groups"]:
            recommendations.append("User not in render group: sudo usermod -a -G render $USER")
        
        if not capabilities["drm_devices"]:
            recommendations.append("No DRM devices found. Check if GPU drivers are loaded.")
            
        capabilities["recommendations"] = recommendations
        
        # Test kmsgrab directly to see if it works at all
        try:
            test_result = subprocess.run([
                'ffmpeg', '-f', 'kmsgrab', '-i', '-', '-t', '1', '-f', 'null', '-'
            ], capture_output=True, text=True, timeout=10)
            
            capabilities["kmsgrab_test"] = {
                "return_code": test_result.returncode,
                "stdout": test_result.stdout[:200] if test_result.stdout else "",
                "stderr": test_result.stderr[:200] if test_result.stderr else "",
                "success": test_result.returncode == 0
            }
        except Exception as e:
            capabilities["kmsgrab_test"] = {"error": str(e), "success": False}
        
        return capabilities
    
    async def start_playback(self, stream_key: str, player: str = "mpv", mode: str = "optimized", protocol: str = "rtmp") -> bool:
        """Start optimal resolution playback using display capabilities"""
        try:
            if self.player_process:
                await self.stop_playback()
            
            if protocol == "rtmp":
                stream_url = f"{SRS_RTMP_URL}/{stream_key}"
            elif protocol == "http_flv":
                stream_url = f"{SRS_HTTP_FLV_URL}/{stream_key}.flv"
            elif protocol == "hls":
                stream_url = f"{SRS_HLS_URL}/{stream_key}.m3u8"
            else:
                raise ValueError(f"Unsupported protocol: {protocol}")
            
            # Get optimal connector and device
            optimal_connector, optimal_device = self.get_optimal_connector_and_device()
            
            # Try capability-matched optimal commands first, then legacy fallbacks
            methods_to_try = [
                # Method 1: Optimal resolution-matched command
                (self.get_optimal_player_command(player, "stream"), f"{player} optimal resolution"),
                # Method 2: Legacy fallback if optimal fails
                (PLAYER_COMMANDS.get(player, {}).get(mode, 
                    PLAYER_COMMANDS.get(player, {}).get("optimized", 
                        ["mpv", "--vo=drm", "--fs", "--quiet"])).copy(), f"{player} {mode} legacy"),
                # Method 3: Basic fallback
                (PLAYER_COMMANDS.get(player, {}).get("basic", 
                    ["mpv", "--vo=drm", "--fs", "--quiet"]).copy(), f"{player} basic legacy")
            ]
            
            last_error = None
            for cmd_template, method_name in methods_to_try:
                try:
                    cmd = cmd_template.copy()
                    cmd.append(stream_url)
                    
                    # Set environment for optimal DRM device
                    env = os.environ.copy()
                    env.update({
                        'DRM_DEVICE': optimal_device,
                        'DRM_CONNECTOR': optimal_connector
                    })
                    
                    logging.info(f"Trying playback method: {method_name}")
                    self.player_process = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    
                    # Check if it starts successfully
                    await asyncio.sleep(2.0)  # Give more time for DRM initialization
                    
                    if self.player_process.poll() is None:
                        # Still running, likely success
                        self.current_stream = stream_key
                        self.current_protocol = protocol
                        self.current_player = f"{player}_{method_name.replace(' ', '_')}"
                        logging.info(f"Successfully started {method_name} playback of {stream_key} via {protocol}")
                        return True
                    else:
                        # Process died, check output
                        stdout, stderr = self.player_process.communicate()
                        output = stderr.decode() if stderr else stdout.decode()
                        
                        # Check for permission errors specifically
                        if "Permission denied" in output:
                            logging.warning(f"Method '{method_name}' failed: Permission denied")
                            last_error = f"{method_name}: Permission denied - try running as sudo"
                        elif "VO: [drm]" in output:
                            logging.info(f"Method '{method_name}' worked but exited - normal for some streams")
                            # This might actually be success for some stream types
                            self.current_stream = stream_key
                            self.current_protocol = protocol
                            self.current_player = f"{player}_{method_name.replace(' ', '_')}"
                            return True
                        else:
                            logging.warning(f"Method '{method_name}' failed: {output}")
                            last_error = f"{method_name}: {output}"
                        
                        self.player_process = None
                        
                except Exception as e:
                    logging.error(f"Exception with method '{method_name}': {e}")
                    last_error = f"{method_name}: {str(e)}"
                    if self.player_process:
                        try:
                            self.player_process.terminate()
                        except:
                            pass
                        self.player_process = None
                    continue
            
            # All methods failed
            raise Exception(f"All playback methods failed. Last error: {last_error}")
            
        except Exception as e:
            logging.error(f"Failed to start {player} playback: {e}")
            return False
    
    async def stop_playback(self) -> bool:
        """Stop current playback and return to background with seamless transition"""
        try:
            if self.player_process:
                old_protocol = self.current_protocol
                
                # Show background for seamless transition 
                if old_protocol != "background":
                    await self.show_background()
                    
                    # If using framebuffer, no delay needed - it's instant
                    # If using fallback, minimal delay for startup
                    if not self.framebuffer.is_available:
                        await asyncio.sleep(0.1)  # Reduced from 0.2s
                
                self.player_process.terminate()
                self.player_process.wait(timeout=5)
                self.player_process = None
                
                self.current_stream = None
                self.current_protocol = None
                self.current_player = None
                
                logging.info("Stopped playback with seamless background transition")
                
            return True
        except Exception as e:
            logging.error(f"Failed to stop playback: {e}")
            return False
    
    async def switch_stream(self, new_stream_key: str) -> bool:
        """Quickly switch to a different stream using same player/settings"""
        if not self.player_process:
            return await self.start_playback(new_stream_key)
            
        current_player = self.current_player or 'mpv'
        current_protocol = self.current_protocol or 'rtmp'
        
        await self.stop_playback()
        return await self.start_playback(new_stream_key, current_player, "optimized", current_protocol)
    
    async def switch_player(self, new_player: str, mode: str = "optimized") -> bool:
        """Switch to different player while keeping same stream"""
        if not self.current_stream:
            return False
            
        stream_key = self.current_stream
        protocol = self.current_protocol or 'rtmp'
        
        await self.stop_playback()
        return await self.start_playback(stream_key, new_player, mode, protocol)
    
    async def display_image(self, image_path: str, duration: int = 10) -> bool:
        """Display an image on screen using DRM acceleration with better fallback handling"""
        try:
            if self.player_process:
                await self.stop_playback()
            
            # Headless Pi4 DRM display methods - no X11 dependencies
            methods = [
                # Method 1: DRM with sudo (fixes permission issues)
                ([
                    "sudo", "mpv", "--vo=drm", "--fs", "--quiet", "--loop=inf",
                    "--no-input-default-bindings", "--no-osc", image_path
                ], {}, "DRM with sudo (Recommended for headless)"),
                
                # Method 2: DRM Direct (if permissions are fixed)
                ([
                    "mpv", "--vo=drm", "--fs", "--quiet", "--loop=inf",
                    "--no-input-default-bindings", "--no-osc", image_path
                ], {}, "DRM Direct"),
                
                # Method 3: DRM with specific mode
                ([
                    "mpv", "--vo=drm", "--drm-mode=1920x1080", "--fs", "--quiet", "--loop=inf",
                    "--no-input-default-bindings", "--no-osc", image_path
                ], {}, "DRM with mode specification"),
                
                # Method 4: DRM with sudo and mode
                ([
                    "sudo", "mpv", "--vo=drm", "--drm-mode=1920x1080", "--fs", "--quiet", "--loop=inf",
                    "--no-input-default-bindings", "--no-osc", image_path
                ], {}, "DRM + sudo + mode"),
                
                # Method 5: Framebuffer fallback (if available)
                ([
                    "mpv", "--vo=drm", "--drm-device=/dev/dri/card0", "--fs", "--quiet", "--loop=inf",
                    "--no-input-default-bindings", "--no-osc", image_path
                ], {}, "DRM with device specification"),
                
                # Method 6: Last resort - try basic mpv (will likely fail in headless)
                ([
                    "mpv", "--fs", "--quiet", image_path
                ], {}, "Basic MPV (likely to fail headless)"),
            ]
            
            last_error = None
            success_method = None
            for cmd, extra_env, method_name in methods:
                try:
                    env = os.environ.copy()
                    env.update(extra_env)
                    env.update({
                        'DRM_DEVICE': '/dev/dri/card0',
                        'DRM_CONNECTOR': self.drm_connector
                    })
                    
                    logging.info(f"Trying image display method: {method_name}")
                    
                    self.player_process = subprocess.Popen(
                        cmd, 
                        env=env,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE
                    )
                    
                    # Check for successful VO initialization (the real indicator of success)
                    await asyncio.sleep(1.0)
                    if self.player_process.poll() is None:
                        # Process is still running - but let's check if it actually initialized video output
                        # Read some output to see if we got VO confirmation
                        try:
                            # Non-blocking read of initial output
                            stdout, stderr = self.player_process.communicate(timeout=0.1)
                        except subprocess.TimeoutExpired:
                            # Process still running, get current output  
                            pass
                            
                        # Check if we're still running after a moment
                        if self.player_process.poll() is None:
                            binary = cmd[1] if cmd[0] == 'sudo' else cmd[0]
                            self.current_player = f"{binary}_{method_name.replace(' ', '_')}"
                            success_method = method_name
                            logging.info(f"Successfully using {method_name} to display image")
                            break
                        
                    # Process exited, check what happened
                    try:
                        stdout, stderr = self.player_process.communicate(timeout=1.0)
                        output = stderr.decode() if stderr else stdout.decode() if stdout else ""
                        
                        # Check if it actually displayed something (VO output means success)
                        if "VO: [" in output and ("drm]" in output or "gpu]" in output):
                            logging.info(f"Method '{method_name}' worked but exited (normal for timed display)")
                            binary = cmd[1] if cmd[0] == 'sudo' else cmd[0]
                            self.current_player = f"{binary}_{method_name.replace(' ', '_')}"
                            success_method = method_name
                            
                            # Restart for continuous display if needed
                            if duration == 0:  # Background display
                                self.player_process = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                            break
                        else:
                            error_msg = output if output else "Process exited without VO output"
                            logging.warning(f"Method '{method_name}' failed: {error_msg}")
                            self.player_process = None
                            last_error = f"{method_name}: {error_msg}"
                            continue
                            
                    except subprocess.TimeoutExpired:
                        # Still running, this is success
                        binary = cmd[1] if cmd[0] == 'sudo' else cmd[0]
                        self.current_player = f"{binary}_{method_name.replace(' ', '_')}"
                        success_method = method_name
                        logging.info(f"Successfully using {method_name} to display image (process running)")
                        break
                        
                except FileNotFoundError:
                    logging.debug(f"Binary {cmd[0]} not found for method: {method_name}")
                    last_error = f"{method_name}: Binary not found"
                    continue
                except Exception as e:
                    logging.warning(f"Failed method '{method_name}': {e}")
                    last_error = f"{method_name}: {str(e)}"
                    if self.player_process:
                        try:
                            self.player_process.terminate()
                        except:
                            pass
                        self.player_process = None
                    continue
            else:
                raise Exception(f"No suitable image display method found. Tried all methods. Last error: {last_error}")
            
            self.current_stream = f"image:{image_path}"
            self.current_protocol = "image" if duration > 0 else "background"
            
            if duration > 0:
                asyncio.create_task(self._auto_close_image(duration))
            
            logging.info(f"Displaying image {image_path} for {duration}s using method: {success_method}")
            return True
        except Exception as e:
            logging.error(f"Failed to display image: {e}")
            return False
    
    async def _auto_close_image(self, duration: int):
        """Auto-close image after specified duration"""
        await asyncio.sleep(duration)
        if self.current_protocol == "image":
            await self.stop_playback()
    
    async def save_and_display_image(self, image_data: str, duration: int = 10) -> bool:
        """Save base64 image data and display it with DRM acceleration"""
        try:
            temp_dir = Path("/tmp/stream_images")
            temp_dir.mkdir(exist_ok=True)
            
            image_bytes = base64.b64decode(image_data)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            image_path = temp_dir / f"display_{timestamp}.jpg"
            
            with open(image_path, "wb") as f:
                f.write(image_bytes)
            
            return await self.display_image(str(image_path), duration)
            
        except Exception as e:
            logging.error(f"Failed to save and display image: {e}")
            return False
    
    async def show_background(self):
        """Show the default background image using framebuffer or DRM fallback"""
        try:
            if os.path.exists(DEFAULT_BACKGROUND_PATH):
                # Try framebuffer first for instant, seamless display
                if self.framebuffer.is_available:
                    success = self.framebuffer.display_image(DEFAULT_BACKGROUND_PATH)
                    if success:
                        logging.info("Background displayed on framebuffer")
                        return
                    else:
                        logging.warning("Framebuffer display failed, trying fallback")
                
                # Fallback to original mpv method for non-framebuffer environments
                await self.display_image(DEFAULT_BACKGROUND_PATH, duration=0)
                logging.info("Background displayed via fallback method")
            else:
                logging.warning("Default background not found")
        except Exception as e:
            logging.error(f"Failed to show background: {e}")

    async def play_youtube(self, youtube_url: str, duration: Optional[int] = None) -> bool:
        """Play YouTube video with optimal resolution and performance"""
        try:
            if self.player_process:
                await self.stop_playback()
            
            # Get optimal display configuration
            optimal_connector, optimal_device = self.get_optimal_connector_and_device()
            width, height, refresh = self.display_detector.get_resolution_for_content_type("youtube")
            
            # Choose YouTube quality based on display resolution
            if height >= 2160:
                youtube_quality = "best[height<=2160]"  # 4K
            elif height >= 1440:
                youtube_quality = "best[height<=1440]"  # 1440p  
            elif height >= 1080:
                youtube_quality = "best[height<=1080]"  # 1080p
            elif height >= 720:
                youtube_quality = "best[height<=720]"   # 720p
            else:
                youtube_quality = "best[height<=480]"   # 480p fallback
            
            # Performance-optimized configs for optimal resolution
            configs = [
                # Method 1: Optimal quality + hardware decode
                [
                    "mpv", "--vo=drm", f"--drm-device={optimal_device}", f"--drm-connector={optimal_connector}",
                    "--hwdec=v4l2m2m", "--fs", "--quiet", "--no-input-default-bindings",
                    f"--ytdl-format={youtube_quality}", "--vd-lavc-dr=yes", "--cache=yes"
                ],
                # Method 2: Reduced quality for stability
                [
                    "mpv", "--vo=drm", f"--drm-device={optimal_device}", f"--drm-connector={optimal_connector}",
                    "--hwdec=v4l2m2m", "--fs", "--quiet", "--no-input-default-bindings",
                    "--ytdl-format=best[height<=720]", "--profile=fast"
                ],
                # Method 3: Low quality but stable
                [
                    "mpv", "--vo=drm", f"--drm-device={optimal_device}", f"--drm-connector={optimal_connector}",
                    "--fs", "--quiet", "--no-input-default-bindings",
                    "--ytdl-format=best[height<=480]", "--profile=low-latency"
                ],
                # Method 4: Basic fallback
                [
                    "mpv", "--vo=drm", f"--drm-device={optimal_device}", f"--drm-connector={optimal_connector}",
                    "--fs", "--quiet", "--no-input-default-bindings"
                ]
            ]
            
            last_error = None
            success_method = None
            for i, base_cmd in enumerate(configs, 1):
                try:
                    cmd = base_cmd.copy()
                    if duration:
                        cmd.extend([f"--end={duration}"])
                    cmd.append(youtube_url)
                    
                    # Set environment for DRM
                    env = os.environ.copy()
                    env.update({
                        'DRM_DEVICE': '/dev/dri/card1'
                    })
                    
                    # Get method name for logging
                    if "height<=480" in str(base_cmd):
                        method_name = "480p + HW decode"
                    elif "height<=360" in str(base_cmd):
                        method_name = "360p smooth"
                    elif "low-latency" in str(base_cmd):
                        method_name = "Low latency"
                    else:
                        method_name = "Standard quality"
                    
                    logging.info(f"YouTube performance attempt {i}/4: {method_name}")
                    
                    self.player_process = subprocess.Popen(
                        cmd, 
                        env=env,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE
                    )
                    
                    # Give YouTube time to start
                    await asyncio.sleep(5.0)
                    
                    if self.player_process.poll() is None:
                        # Still running = success!
                        self.current_player = f"mpv_{method_name.replace(' ', '_')}"
                        success_method = method_name
                        logging.info(f"✅ YouTube SUCCESS with {method_name}")
                        break
                    else:
                        # Process died, check why
                        stdout, stderr = self.player_process.communicate()
                        output = stderr.decode() if stderr else stdout.decode()
                        
                        if "VO: [drm]" in output:
                            # DRM worked but video failed
                            logging.info(f"⚠️  {method_name}: DRM OK but video failed - trying next")
                            last_error = f"{method_name}: DRM OK, video issue"
                        else:
                            logging.info(f"❌ {method_name}: Failed")
                            last_error = f"{method_name}: {output[:100] if output else 'Unknown'}"
                        
                        self.player_process = None
                        continue
                        
                except Exception as e:
                    logging.warning(f"Exception with {method_name}: {e}")
                    last_error = str(e)
                    if self.player_process:
                        try:
                            self.player_process.terminate()
                        except:
                            pass
                        self.player_process = None
                    continue
            else:
                raise Exception(f"YouTube failed with all performance optimizations. Last error: {last_error}")
            
            self.current_stream = f"youtube:{youtube_url}"
            self.current_protocol = "youtube"
            
            if duration:
                asyncio.create_task(self._auto_return_to_background(duration))
            else:
                asyncio.create_task(self._monitor_youtube_playback())
            
            logging.info(f"🎬 Playing YouTube with {success_method} for {duration or 'full'} duration")
            return True
            
        except Exception as e:
            logging.error(f"YouTube playback failed: {e}")
            await self.show_background()
            return False
    
    async def _auto_return_to_background(self, duration: int):
        """Return to background after specified duration"""
        await asyncio.sleep(duration)
        if self.current_protocol == "youtube":
            await self.stop_playback()
    
    async def _monitor_youtube_playback(self):
        """Monitor YouTube playback and return to background when finished"""
        try:
            if self.player_process:
                await self._wait_for_process(self.player_process)
                if self.current_protocol == "youtube":
                    await self.show_background()
        except Exception as e:
            logging.error(f"Error monitoring YouTube playback: {e}")
            await self.show_background()
    
    async def _wait_for_process(self, process):
        """Wait for a process to finish"""
        while process.poll() is None:
            await asyncio.sleep(1)
        return process.poll()
    
    async def _check_display_setup(self) -> Dict[str, bool]:
        """Check what DRM/display methods are available"""
        available = {
            'drm': False,
            'drm_connectors': [],
            'gpu_memory': self.gpu_memory,
            'v4l2m2m': False,
            'viewers': []
        }
        
        # Check DRM access
        try:
            drm_devices = []
            drm_path = '/dev/dri'
            if os.path.exists(drm_path):
                for device in os.listdir(drm_path):
                    device_path = os.path.join(drm_path, device)
                    if os.access(device_path, os.R_OK | os.W_OK):
                        drm_devices.append(device)
                        available['drm'] = True
            available['drm_devices'] = drm_devices
        except:
            pass
            
        # Check DRM connectors
        try:
            drm_path = "/sys/class/drm"
            for item in os.listdir(drm_path):
                if item.startswith("card0-"):
                    connector_path = os.path.join(drm_path, item, "status")
                    if os.path.exists(connector_path):
                        with open(connector_path, 'r') as f:
                            status = f.read().strip()
                        if status == "connected":
                            connector_name = item.replace("card0-", "")
                            available['drm_connectors'].append(connector_name)
        except:
            pass
            
        # Check V4L2M2M hardware acceleration
        try:
            v4l2_devices = [f for f in os.listdir('/dev') if f.startswith('video')]
            if v4l2_devices:
                available['v4l2m2m'] = True
        except:
            pass
            
        # Check available image viewers with DRM capabilities
        viewers = ['mpv', 'feh', 'eog', 'gpicview']
        for viewer in viewers:
            try:
                subprocess.run(['which', viewer], capture_output=True, check=True)
                available['viewers'].append(viewer)
            except:
                pass
                
        return available
    
    def get_srs_stats(self) -> Dict[str, Any]:
        """Get SRS server statistics"""
        try:
            response = requests.get(f"{SRS_API_URL}/streams", timeout=5)
            return response.json() if response.status_code == 200 else {}
        except Exception as e:
            logging.error(f"Failed to get SRS stats: {e}")
            return {}
    
    def get_system_stats(self) -> Dict[str, Any]:
        """Get system resource usage with Pi4-specific optimizations"""
        stats = {
            "cpu_percent": psutil.cpu_percent(),
            "memory_percent": psutil.virtual_memory().percent,
            "disk_usage": psutil.disk_usage('/').percent,
            "temperature": self._get_cpu_temp(),
            "gpu_memory": self.gpu_memory,
            "drm_connector": self.drm_connector
        }
        
        # Add GPU-specific stats for Pi4
        try:
            # Check GPU temperature
            result = subprocess.run(['vcgencmd', 'measure_temp'], 
                                  capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                temp_str = result.stdout.strip()
                if 'temp=' in temp_str:
                    gpu_temp = float(temp_str.split('=')[1].replace("'C", ""))
                    stats['gpu_temperature'] = gpu_temp
        except:
            pass
            
        # Check GPU frequency
        try:
            result = subprocess.run(['vcgencmd', 'measure_clock', 'core'], 
                                  capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                freq_str = result.stdout.strip()
                if 'frequency(' in freq_str:
                    gpu_freq = int(freq_str.split('=')[1]) // 1000000  # Convert to MHz
                    stats['gpu_frequency_mhz'] = gpu_freq
        except:
            pass
            
        # Check memory split
        try:
            result = subprocess.run(['vcgencmd', 'get_mem', 'arm'], 
                                  capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                arm_mem = int(result.stdout.strip().replace('arm=', '').replace('M', ''))
                stats['arm_memory'] = arm_mem
        except:
            pass
            
        return stats
    
    def _get_cpu_temp(self) -> Optional[float]:
        """Get Pi CPU temperature"""
        try:
            with open('/sys/class/thermal/thermal_zone0/temp', 'r') as f:
                temp = float(f.read().strip()) / 1000.0
                return temp
        except:
            return None
    
    async def generate_and_display_qr_code(self, content: str, duration: Optional[int] = None) -> bool:
        """Generate QR code with text overlay and display it"""
        try:
            temp_dir = Path("/tmp/stream_images")
            temp_dir.mkdir(exist_ok=True)
            
            # Get optimal display resolution
            width, height, refresh = self.display_detector.get_resolution_for_content_type("image")
            
            # Create QR code
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4,
            )
            qr.add_data(content)
            qr.make(fit=True)
            
            # Generate QR code image
            qr_image = qr.make_image(fill_color="black", back_color="white")
            
            # Calculate QR code size (make it as large as possible while leaving room for text)
            text_height = height // 8  # Reserve top portion for text
            available_height = height - text_height
            available_width = width
            
            # QR code should be square, so use the smaller dimension
            qr_size = min(available_width, available_height) - 40  # Leave some margin
            
            # Resize QR code
            qr_image = qr_image.resize((qr_size, qr_size), Image.Resampling.NEAREST)
            
            # Create final image with display resolution
            final_image = Image.new('RGB', (width, height), 'white')
            
            # Paste QR code centered in bottom portion
            qr_x = (width - qr_size) // 2
            qr_y = text_height + (available_height - qr_size) // 2
            final_image.paste(qr_image, (qr_x, qr_y))
            
            # Add text at the top
            draw = ImageDraw.Draw(final_image)
            
            # Try to load a font, fallback to default
            try:
                font_size = text_height // 3
                font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size)
            except:
                try:
                    font = ImageFont.load_default()
                except:
                    font = None
            
            # Split content into lines if it's too long
            max_chars_per_line = width // (font_size // 2) if font else 50
            lines = []
            words = content.split()
            current_line = ""
            
            for word in words:
                if len(current_line + " " + word) <= max_chars_per_line:
                    current_line += " " + word if current_line else word
                else:
                    if current_line:
                        lines.append(current_line)
                    current_line = word
            if current_line:
                lines.append(current_line)
            
            # Limit to 3 lines
            lines = lines[:3]
            
            # Draw text centered
            line_height = font_size + 10 if font else 20
            total_text_height = len(lines) * line_height
            start_y = (text_height - total_text_height) // 2
            
            for i, line in enumerate(lines):
                if font:
                    bbox = draw.textbbox((0, 0), line, font=font)
                    text_width = bbox[2] - bbox[0]
                else:
                    text_width = len(line) * 10  # rough estimate
                
                text_x = (width - text_width) // 2
                text_y = start_y + i * line_height
                
                if font:
                    draw.text((text_x, text_y), line, fill="black", font=font)
                else:
                    draw.text((text_x, text_y), line, fill="black")
            
            # Save the image
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            image_path = temp_dir / f"qrcode_{timestamp}.jpg"
            final_image.save(str(image_path), "JPEG", quality=95)
            
            # Display the image (duration=0 means forever)
            display_duration = duration if duration is not None else 0
            return await self.display_image(str(image_path), display_duration)
            
        except Exception as e:
            logging.error(f"Failed to generate and display QR code: {e}")
            return False
    
    def cleanup(self):
        """Clean up all resources"""
        try:
            # Clean up any running processes
            if self.player_process:
                self.player_process.terminate()
            if self.background_process:
                self.background_process.terminate()
            if self.screen_stream_process:
                self.screen_stream_process.terminate()
            
            # Clean up framebuffer resources
            if hasattr(self, 'framebuffer'):
                self.framebuffer.cleanup()
                
            logging.info("StreamManager cleanup completed")
        except Exception as e:
            logging.error(f"Error during cleanup: {e}")

# Global stream manager instance
stream_manager = StreamManager()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle (startup and shutdown)"""
    # Startup
    logging.info("Starting HSG Canvas application...")
    
    # Create static directory if it doesn't exist
    os.makedirs("static", exist_ok=True)
    await stream_manager.create_default_background()
    await asyncio.sleep(2)
    await stream_manager.show_background()
    
    # Log DRM capabilities at startup
    capabilities = await stream_manager._check_display_setup()
    logging.info(f"DRM Capabilities: {capabilities}")
    
    yield  # Application runs here
    
    # Shutdown
    logging.info("Shutting down HSG Canvas application...")
    await stream_manager.stop_playback()
    for stream_key in list(stream_manager.active_streams.keys()):
        await stream_manager.stop_stream(stream_key)

# FastAPI app initialization with lifespan
app = FastAPI(
    title="HSG Canvas",
    version="2.0.0",
    description="Control media streams and playback on Raspberry Pi with GPU acceleration",
    lifespan=lifespan
)

# Serve static files (for CSS/JS if needed)
app.mount("/static", StaticFiles(directory="static"), name="static")

# API Routes
@app.get("/", response_class=HTMLResponse)
async def web_interface():
    """Serve the web interface"""
    try:
        with open("index.html", "r") as f:
            return f.read()
    except FileNotFoundError:
        return """
        <h1>Error: index.html not found</h1>
        <p>Please create an index.html file in the same directory as the Python server.</p>
        <p>You can access the API documentation at <a href="/docs">/docs</a></p>
        """

@app.post("/streams/{stream_key}/start")
async def start_stream(stream_key: str, source_url: str, protocol: str = "rtmp"):
    """Start publishing a GPU-accelerated stream using specified protocol"""
    success = await stream_manager.start_stream(stream_key, source_url, protocol)
    if success:
        return {"message": f"GPU-accelerated stream {stream_key} started via {protocol.upper()}"}
    else:
        raise HTTPException(status_code=500, detail=f"Failed to start {protocol} stream")

@app.delete("/streams/{stream_key}")
async def stop_stream(stream_key: str):
    """Stop a specific stream"""
    success = await stream_manager.stop_stream(stream_key)
    if success:
        return {"message": f"Stream {stream_key} stopped"}
    else:
        raise HTTPException(status_code=404, detail="Stream not found")

@app.post("/screen-stream/{stream_key}/start")
async def start_screen_stream(stream_key: str, protocol: str = "rtmp"):
    """Start streaming the display output"""
    success = await stream_manager.start_screen_stream(stream_key, protocol)
    if success:
        return {"message": f"Screen streaming started: {stream_key} via {protocol.upper()}"}
    else:
        raise HTTPException(status_code=500, detail=f"Failed to start screen streaming via {protocol}")

@app.delete("/screen-stream/stop")
async def stop_screen_stream():
    """Stop screen streaming"""
    success = await stream_manager.stop_screen_stream()
    if success:
        return {"message": "Screen streaming stopped"}
    else:
        raise HTTPException(status_code=404, detail="No active screen stream")

@app.get("/screen-stream/status")
async def get_screen_stream_status():
    """Get screen streaming status"""
    return stream_manager.get_screen_stream_info()

@app.get("/screen-stream/capabilities")
async def get_screen_capture_capabilities():
    """Check FFmpeg and DRM capabilities for screen capture"""
    return stream_manager.check_screen_capture_capabilities()

@app.post("/playback/{stream_key}/start")
async def start_playback(stream_key: str, player: str = "mpv", mode: str = "optimized", protocol: str = "rtmp"):
    """Start DRM-accelerated playback with specified player"""
    success = await stream_manager.start_playback(stream_key, player, mode, protocol)
    if success:
        return {"message": f"Started DRM-accelerated {player} playback of {stream_key} via {protocol}"}
    else:
        raise HTTPException(status_code=500, detail="Failed to start playback")

@app.delete("/playback/stop")
async def stop_playback():
    """Stop current playback"""
    success = await stream_manager.stop_playback()
    if success:
        return {"message": "Playback stopped"}
    else:
        raise HTTPException(status_code=500, detail="Failed to stop playback")

@app.post("/playback/switch/{stream_key}")
async def switch_stream(stream_key: str):
    """Quickly switch to different stream"""
    success = await stream_manager.switch_stream(stream_key)
    if success:
        return {"message": f"Switched to stream {stream_key}"}
    else:
        raise HTTPException(status_code=500, detail="Failed to switch stream")

@app.post("/playback/player/{player}")
async def switch_player(player: str, mode: str = "optimized"):
    """Switch to different DRM-accelerated player"""
    success = await stream_manager.switch_player(player, mode)
    if success:
        return {"message": f"Switched to DRM-accelerated {player} player"}
    else:
        raise HTTPException(status_code=500, detail="Failed to switch player")

@app.post("/playback/youtube")
async def play_youtube_video(request: YoutubePlayRequest):
    """Play a YouTube video with DRM acceleration"""
    success = await stream_manager.play_youtube(request.youtube_url, request.duration)
    if success:
        duration_text = f" for {request.duration}s" if request.duration else ""
        return {"message": f"Playing YouTube video with DRM acceleration{duration_text}"}
    else:
        raise HTTPException(status_code=500, detail="Failed to play YouTube video")

@app.post("/display/qrcode")
async def display_qr_code(request: QRCodeRequest):
    """Generate and display a QR code with text overlay"""
    success = await stream_manager.generate_and_display_qr_code(request.content, request.duration)
    if success:
        duration_text = f" for {request.duration}s" if request.duration else " (forever)"
        return {"message": f"Displaying QR code for '{request.content}'{duration_text}"}
    else:
        raise HTTPException(status_code=500, detail="Failed to generate and display QR code")

@app.post("/background/show")
async def show_background():
    """Show the DRM-accelerated background"""
    await stream_manager.show_background()
    return {"message": "Showing DRM-accelerated background"}

@app.post("/background/set")
async def set_background(file: UploadFile = File(...)):
    """Set a new default background image"""
    try:
        image_data = await file.read()
        temp_dir = Path("/tmp/stream_images")
        temp_dir.mkdir(exist_ok=True)
        
        with open(DEFAULT_BACKGROUND_PATH, "wb") as f:
            f.write(image_data)
        
        await stream_manager.show_background()
        return {"message": "Background updated and displayed with DRM acceleration"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to set background: {str(e)}")

@app.post("/display/image")
async def display_image_endpoint(file: UploadFile = File(...), duration: int = 10):
    """Upload and display an image on screen with DRM acceleration"""
    try:
        image_data = await file.read()
        temp_dir = Path("/tmp/stream_images")
        temp_dir.mkdir(exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        image_path = temp_dir / f"upload_{timestamp}_{file.filename}"
        
        with open(image_path, "wb") as f:
            f.write(image_data)
        
        success = await stream_manager.display_image(str(image_path), duration)
        
        if success:
            return {"message": f"Displaying image with DRM acceleration for {duration} seconds", "path": str(image_path)}
        else:
            raise HTTPException(status_code=500, detail="Failed to display image")
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to upload image: {str(e)}")

@app.post("/display/image/base64")
async def display_image_base64(request: ImageDisplayRequest):
    """Display a base64 encoded image with DRM acceleration"""
    success = await stream_manager.save_and_display_image(request.image_data, request.duration)
    if success:
        return {"message": f"Displaying image with DRM acceleration for {request.duration} seconds"}
    else:
        raise HTTPException(status_code=500, detail="Failed to display image")

# HDMI-CEC API Endpoints
@app.post("/cec/tv/power-on")
async def power_on_tv():
    """Turn on TV/monitor via HDMI-CEC"""
    result = await stream_manager.cec_manager.power_on_tv()
    if result["success"]:
        return {"message": result["message"], "tv_address": result["tv_address"]}
    else:
        raise HTTPException(status_code=500, detail=result["message"])

@app.post("/cec/tv/power-off")
async def power_off_tv():
    """Put TV/monitor in standby via HDMI-CEC"""
    result = await stream_manager.cec_manager.power_off_tv()
    if result["success"]:
        return {"message": result["message"], "tv_address": result["tv_address"]}
    else:
        raise HTTPException(status_code=500, detail=result["message"])

@app.get("/cec/status")
async def get_cec_status():
    """Get HDMI-CEC status and TV power state"""
    status = stream_manager.cec_manager.get_status()
    
    # Also get TV power status if CEC is available
    if status["available"]:
        power_result = await stream_manager.cec_manager.get_tv_power_status()
        status["tv_power"] = power_result
    else:
        status["tv_power"] = {"success": False, "power_status": "unavailable"}
    
    return status

@app.post("/cec/scan")
async def scan_cec_devices():
    """Scan for HDMI-CEC devices"""
    result = await stream_manager.cec_manager.scan_devices()
    return result

@app.get("/streams")
async def list_streams():
    """List all active streams and current playback status"""
    streams = {}
    for key, info in stream_manager.active_streams.items():
        streams[key] = {
            "source_url": info["source_url"],
            "protocol": info["protocol"],
            "started_at": info["started_at"],
            "status": info["status"]
        }
    
    return {
        "active_streams": streams,
        "current_playback": {
            "stream": stream_manager.current_stream,
            "protocol": stream_manager.current_protocol,
            "player": stream_manager.current_player
        }
    }

@app.get("/diagnostics")
async def get_diagnostics():
    """Get comprehensive DRM and system diagnostics"""
    diag = await stream_manager._check_display_setup()
    
    # Additional Pi4-specific diagnostics
    diag.update({
        "user": os.getenv('USER', 'unknown'),
        "display_env": os.getenv('DISPLAY', 'not_set'),
        "groups": os.getgroups() if hasattr(os, 'getgroups') else [],
        "drm_connector_detected": stream_manager.drm_connector,
        "gpu_memory_split": stream_manager.gpu_memory,
        "process_info": {
            "current_player": stream_manager.current_player,
            "current_stream": stream_manager.current_stream,
            "player_running": stream_manager.player_process is not None
        }
    })
    
    # Check DRM device permissions in detail
    try:
        drm_path = '/dev/dri'
        if os.path.exists(drm_path):
            diag["drm_devices_detailed"] = []
            for device in os.listdir(drm_path):
                device_path = os.path.join(drm_path, device)
                stat_info = os.stat(device_path)
                diag["drm_devices_detailed"].append({
                    "device": device,
                    "path": device_path,
                    "readable": os.access(device_path, os.R_OK),
                    "writable": os.access(device_path, os.W_OK),
                    "mode": oct(stat_info.st_mode),
                    "uid": stat_info.st_uid,
                    "gid": stat_info.st_gid
                })
    except Exception as e:
        diag["drm_error"] = str(e)
    
    # Check V4L2 devices for hardware acceleration
    try:
        v4l2_devices = []
        for device in os.listdir('/dev'):
            if device.startswith('video'):
                device_path = f'/dev/{device}'
                v4l2_devices.append({
                    "device": device,
                    "path": device_path,
                    "readable": os.access(device_path, os.R_OK),
                    "writable": os.access(device_path, os.W_OK)
                })
        diag["v4l2_devices"] = v4l2_devices
    except Exception as e:
        diag["v4l2_error"] = str(e)
    
    # Check Pi4 GPU info
    pi_gpu_info = {}
    try:
        # GPU temperature
        result = subprocess.run(['vcgencmd', 'measure_temp'], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            pi_gpu_info["temperature"] = result.stdout.strip()
    except:
        pass
        
    try:
        # GPU frequency
        result = subprocess.run(['vcgencmd', 'measure_clock', 'core'], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            pi_gpu_info["core_frequency"] = result.stdout.strip()
    except:
        pass
        
    try:
        # Memory configuration
        for mem_type in ['arm', 'gpu']:
            result = subprocess.run(['vcgencmd', 'get_mem', mem_type], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                pi_gpu_info[f"{mem_type}_memory"] = result.stdout.strip()
    except:
        pass
    
    diag["pi4_gpu_info"] = pi_gpu_info
    
    # HDMI-CEC diagnostics
    diag["hdmi_cec"] = stream_manager.cec_manager.get_status()
    
    return diag

@app.get("/test/drm")
async def test_drm_acceleration():
    """Test DRM acceleration capabilities"""
    test_results = {
        "timestamp": datetime.now().isoformat(),
        "tests": []
    }
    
    # Test 1: DRM device access
    try:
        drm_test = {"name": "DRM Device Access", "status": "pass", "details": []}
        
        for device in os.listdir('/dev/dri'):
            device_path = f'/dev/dri/{device}'
            can_read = os.access(device_path, os.R_OK)
            can_write = os.access(device_path, os.W_OK)
            drm_test["details"].append({
                "device": device,
                "readable": can_read,
                "writable": can_write,
                "status": "pass" if can_read and can_write else "fail"
            })
            
        if not any(d["status"] == "pass" for d in drm_test["details"]):
            drm_test["status"] = "fail"
            
        test_results["tests"].append(drm_test)
    except Exception as e:
        test_results["tests"].append({
            "name": "DRM Device Access",
            "status": "fail",
            "error": str(e)
        })
    
    # Test 2: DRM connector detection
    try:
        connector_test = {"name": "DRM Connector Detection", "status": "pass"}
        connector_test["detected_connector"] = stream_manager.drm_connector
        connector_test["available_connectors"] = []
        
        drm_path = "/sys/class/drm"
        for item in os.listdir(drm_path):
            if item.startswith("card0-"):
                connector_path = os.path.join(drm_path, item, "status")
                if os.path.exists(connector_path):
                    with open(connector_path, 'r') as f:
                        status = f.read().strip()
                    connector_name = item.replace("card0-", "")
                    connector_test["available_connectors"].append({
                        "name": connector_name,
                        "status": status,
                        "connected": status == "connected"
                    })
        
        test_results["tests"].append(connector_test)
    except Exception as e:
        test_results["tests"].append({
            "name": "DRM Connector Detection",
            "status": "fail",
            "error": str(e)
        })
    
    # Test 3: V4L2M2M hardware acceleration
    try:
        v4l2_test = {"name": "V4L2M2M Hardware Acceleration", "status": "pass"}
        v4l2_devices = [f for f in os.listdir('/dev') if f.startswith('video')]
        v4l2_test["devices"] = v4l2_devices
        
        if not v4l2_devices:
            v4l2_test["status"] = "fail"
            v4l2_test["message"] = "No V4L2 devices found"
            
        test_results["tests"].append(v4l2_test)
    except Exception as e:
        test_results["tests"].append({
            "name": "V4L2M2M Hardware Acceleration",
            "status": "fail",
            "error": str(e)
        })
    
    # Test 4: MPV DRM capabilities
    try:
        mpv_test = {"name": "MPV DRM Support", "status": "unknown"}
        result = subprocess.run(['mpv', '--vo=help'], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            output = result.stdout
            mpv_test["drm_available"] = 'drm' in output
            mpv_test["gpu_available"] = 'gpu' in output
            mpv_test["status"] = "pass" if mpv_test["drm_available"] else "warning"
            mpv_test["output"] = output
        else:
            mpv_test["status"] = "fail"
            mpv_test["error"] = result.stderr
            
        test_results["tests"].append(mpv_test)
    except Exception as e:
        test_results["tests"].append({
            "name": "MPV DRM Support",
            "status": "fail",
            "error": str(e)
        })
    
    # Test 5: Quick DRM test with mpv
    try:
        quick_test = {"name": "Quick DRM Test", "status": "unknown"}
        
        # Create a quick test image
        test_dir = Path("/tmp/stream_images")
        test_dir.mkdir(exist_ok=True)
        test_image_path = test_dir / "drm_test.jpg"
        
        img = Image.new('RGB', (100, 100), (255, 0, 0))
        img.save(test_image_path, 'JPEG')
        
        # Try to display it briefly with DRM
        cmd = [
            "timeout", "3",  # 3 second timeout
            "mpv", "--vo=drm", "--fs", "--quiet", "--loop=inf", 
            "--drm-connector", stream_manager.drm_connector,
            str(test_image_path)
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        quick_test["exit_code"] = result.returncode
        quick_test["stderr"] = result.stderr
        
        # Exit code 124 means timeout (success), 0 also success
        if result.returncode in [0, 124]:
            quick_test["status"] = "pass"
            quick_test["message"] = "DRM display test successful"
        else:
            quick_test["status"] = "fail"
            quick_test["message"] = "DRM display test failed"
            
        # Clean up test image
        test_image_path.unlink(missing_ok=True)
        
        test_results["tests"].append(quick_test)
    except Exception as e:
        test_results["tests"].append({
            "name": "Quick DRM Test",
            "status": "fail",
            "error": str(e)
        })
    
    # Overall assessment
    passed_tests = sum(1 for test in test_results["tests"] if test["status"] == "pass")
    total_tests = len(test_results["tests"])
    
    test_results["summary"] = {
        "passed": passed_tests,
        "total": total_tests,
        "overall_status": "pass" if passed_tests >= total_tests * 0.8 else "warning" if passed_tests >= total_tests * 0.5 else "fail"
    }
    
    return test_results

@app.post("/background/mode")
async def set_background_mode(request: dict):
    """Set background display mode (static or splitflap_clock)"""
    try:
        mode = request.get("mode", "static")
        if mode not in ["static", "splitflap_clock"]:
            raise HTTPException(status_code=400, detail="Invalid mode. Use 'static' or 'splitflap_clock'")
        
        success = await stream_manager.set_background_mode(mode)
        if success:
            return {"status": "success", "mode": mode}
        else:
            raise HTTPException(status_code=500, detail="Failed to set background mode")
            
    except Exception as e:
        logging.error(f"Failed to set background mode: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/background/mode")
async def get_background_mode():
    """Get current background mode and status"""
    try:
        status = stream_manager.get_background_status()
        return status
    except Exception as e:
        logging.error(f"Failed to get background status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/background/clock/regenerate")
async def regenerate_clock_background():
    """Force regeneration of splitflap clock background"""
    try:
        if stream_manager.background_manager:
            # Clear cache and restart splitflap mode if active
            current_status = stream_manager.get_background_status()
            if current_status.get("mode") == "splitflap_clock":
                await stream_manager.set_background_mode("splitflap_clock")
                return {"status": "success", "message": "Splitflap clock regenerated"}
            else:
                return {"status": "info", "message": "Splitflap clock not active"}
        else:
            raise HTTPException(status_code=500, detail="Background manager not available")
    except Exception as e:
        logging.error(f"Failed to regenerate clock: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/status")
async def get_status():
    """Get overall system and streaming status with DRM info"""
    return {
        "srs_stats": stream_manager.get_srs_stats(),
        "system_stats": stream_manager.get_system_stats(),
        "active_streams": len(stream_manager.active_streams),
        "current_playback": {
            "stream": stream_manager.current_stream,
            "protocol": stream_manager.current_protocol,
            "player": stream_manager.current_player
        },
        "player_running": stream_manager.player_process is not None,
        "drm_info": {
            "connector": stream_manager.drm_connector,
            "gpu_memory": stream_manager.gpu_memory
        }
    }

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy", 
        "timestamp": datetime.now().isoformat(),
        "version": "2.0.0-drm",
        "drm_enabled": True,
        "gpu_memory": stream_manager.gpu_memory
    }

@app.get("/resolution")
async def get_current_resolution():
    """Get current display resolution"""
    try:
        width, height, refresh = stream_manager.display_detector.get_resolution_for_content_type("image")
        return {
            "width": width,
            "height": height,
            "refresh_rate": refresh,
            "resolution_string": f"{width}x{height}@{refresh}Hz"
        }
    except Exception as e:
        logging.error(f"Failed to get resolution: {e}")
        return {
            "width": 1920,
            "height": 1080, 
            "refresh_rate": 60,
            "resolution_string": "1920x1080@60Hz",
            "error": "Could not detect resolution, using default"
        }

@app.get("/docs/quick-start")
async def quick_start_guide():
    """DRM-optimized quick start documentation"""
    return {
        "quick_start": {
            "1_start_stream": "POST /streams/{key}/start?source_url=input.mp4 (GPU-accelerated)",
            "2_start_playback": "POST /playback/{key}/start?player=mpv&protocol=rtmp (DRM-accelerated)",
            "3_switch_stream": "POST /playback/switch/{new_key}",
            "4_stop_playback": "DELETE /playback/stop",
            "5_display_image": "POST /display/image (DRM-accelerated upload)",
            "6_youtube_video": "POST /playback/youtube (DRM-accelerated playback)"
        },
        "drm_optimization": {
            "pi4_gpu_memory": f"{stream_manager.gpu_memory}MB",
            "drm_connector": stream_manager.drm_connector,
            "hardware_acceleration": "V4L2M2M enabled for encoding/decoding",
            "display_method": "Direct DRM/KMS rendering for maximum performance"
        },
        "performance_tips": {
            "recommended_player": "mpv with 'optimized' mode for best DRM performance",
            "gpu_memory_split": "Ensure GPU memory split is at least 128MB (current: " + str(stream_manager.gpu_memory) + "MB)",
            "cooling": "Monitor CPU/GPU temperature for sustained performance",
            "streaming_bitrate": "Use 3-4Mbps for optimal Pi4 performance with hardware encoding"
        },
        "troubleshooting": {
            "drm_test": "GET /test/drm - Comprehensive DRM capability testing",
            "diagnostics": "GET /diagnostics - Detailed system capabilities",
            "permissions": "Ensure user is in 'video' and 'render' groups for DRM access"
        }
    }

# Cleanup is now handled in the lifespan context manager above

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Log startup info
    logging.info("Starting HSG Canvas v2.0.0")
    logging.info(f"Detected DRM connector: {StreamManager().drm_connector}")
    logging.info(f"GPU memory split: {StreamManager()._get_gpu_memory()}MB")
    
    uvicorn.run(app, host="0.0.0.0", port=8000)