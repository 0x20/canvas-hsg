"""
Background Mode Management for HSG Canvas
Handles static background image display with scaling and centering.
"""

import asyncio
import os
import time
import logging
from pathlib import Path
from typing import Optional, Any
from PIL import Image


class BackgroundManager:
    """Manages static background image display"""
    
    def __init__(self, display_detector, framebuffer_manager):
        self.display_detector = display_detector
        self.framebuffer = framebuffer_manager
        
        # Current state
        self.is_running = False
        
        # Static background image path - set to canvas_background.png by default
        self.static_background_image = "/home/hsg/srs_server/canvas_background.png"
        
        # Verify the default background exists
        if not os.path.exists(self.static_background_image):
            logging.warning(f"Default background image not found: {self.static_background_image}")
            self.static_background_image = None
        
        # Paths
        self.temp_dir = Path("/tmp/stream_images")
        self.temp_dir.mkdir(exist_ok=True)
        self.current_background_path = self.temp_dir / "current_background.png"
    
    async def start_static_mode(self) -> bool:
        """Start static background display"""
        try:
            if self.is_running:
                return True
            
            logging.info("Starting static background mode")
            await self._start_static_mode()
            self.is_running = True
            return True
            
        except Exception as e:
            logging.error(f"Failed to start static background mode: {e}")
            return False
    
    async def start_static_mode_with_audio_status(self, show_audio_icon: bool = False) -> bool:
        """Start static background mode with audio status icon"""
        try:
            await self.stop()
            
            logging.info(f"Starting static background mode (audio icon: {show_audio_icon})")
            await self._start_static_mode(show_audio_icon=show_audio_icon)
            self.is_running = True
            return True
            
        except Exception as e:
            logging.error(f"Failed to start static background mode: {e}")
            return False
    
    async def _start_static_mode(self, show_audio_icon: bool = False) -> None:
        """Start static background mode"""
        await self._create_static_background(show_audio_icon=show_audio_icon)
        await self._display_current_background()
    
    async def _create_static_background(self, show_audio_icon: bool = False) -> None:
        """Scale and display static background image to monitor resolution"""
        try:
            # Get optimal resolution
            display_config = self.display_detector.get_optimal_framebuffer_config()
            width, height = display_config['width'], display_config['height']
            
            if not self.static_background_image or not os.path.exists(self.static_background_image):
                # Create a simple fallback background if no image is set
                img = Image.new('RGB', (width, height), (20, 20, 30))
                logging.warning(f"No background image set, using fallback color: {width}x{height}")
            else:
                # Load and scale the static background image
                img = self._scale_image_to_resolution(self.static_background_image, width, height)
                logging.info(f"Scaled background image to: {width}x{height}")
            
            # Save scaled background
            img.save(str(self.current_background_path))
            
        except Exception as e:
            logging.error(f"Failed to create static background: {e}")
            # Create fallback background
            display_config = self.display_detector.get_optimal_framebuffer_config()
            width, height = display_config['width'], display_config['height']
            img = Image.new('RGB', (width, height), (20, 20, 30))
            img.save(str(self.current_background_path))
    
    async def _display_current_background(self) -> None:
        """Display the current background image using MPV with DRM"""
        import subprocess

        if not self.current_background_path.exists():
            raise RuntimeError("No background image to display")

        # Kill any existing display processes
        subprocess.run(["sudo", "pkill", "fbi"], capture_output=True)
        subprocess.run(["sudo", "pkill", "-f", "mpv.*current_background"], capture_output=True)

        # Start MPV with DRM (direct rendering, bypasses framebuffer)
        subprocess.Popen([
            "sudo", "mpv", "--vo=drm", "--fs", "--quiet", "--loop=inf",
            "--no-input-default-bindings", "--no-osc", str(self.current_background_path)
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        logging.info("Background displayed with MPV DRM")
    
    async def _display_with_image_viewer(self) -> None:
        """Display background using image viewer fallback"""
        viewers = ["feh", "eog", "gpicview"]
        
        for viewer in viewers:
            try:
                import subprocess
                # Check if viewer is available
                result = await asyncio.create_subprocess_exec(
                    "which", viewer,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                await result.wait()
                
                if result.returncode == 0:
                    # Start viewer
                    cmd = [viewer, "--fullscreen", "--auto-zoom", str(self.current_background_path)]
                    process = await asyncio.create_subprocess_exec(*cmd)
                    logging.info(f"Started background display with {viewer}")
                    return
                    
            except Exception as e:
                logging.warning(f"Failed to start {viewer}: {e}")
                continue
        
        logging.error("No suitable image viewer found")
    
    def set_background_image(self, image_path: str) -> bool:
        """Set the static background image path"""
        try:
            if not os.path.exists(image_path):
                logging.error(f"Background image not found: {image_path}")
                return False
            
            # Verify it's a valid image
            with Image.open(image_path) as img:
                img.verify()
            
            self.static_background_image = image_path
            logging.info(f"Set background image: {image_path}")
            return True
            
        except Exception as e:
            logging.error(f"Invalid background image {image_path}: {e}")
            return False
    
    def _scale_image_to_resolution(self, image_path: str, target_width: int, target_height: int) -> Image.Image:
        """Scale image to target resolution while preserving aspect ratio"""
        try:
            with Image.open(image_path) as img:
                # Convert to RGB if necessary
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                
                # Get original dimensions
                orig_width, orig_height = img.size
                
                logging.info(f"Original image: {orig_width}x{orig_height}, Target: {target_width}x{target_height}")
                
                # If image already matches target resolution exactly, return as-is
                if orig_width == target_width and orig_height == target_height:
                    logging.info("Image already matches target resolution - no scaling needed")
                    return img.copy()
                
                # Calculate scaling factor to fit within target dimensions
                width_ratio = target_width / orig_width
                height_ratio = target_height / orig_height
                scale_factor = min(width_ratio, height_ratio)
                
                # Calculate new dimensions
                new_width = int(orig_width * scale_factor)
                new_height = int(orig_height * scale_factor)
                
                logging.info(f"Scale factor: {scale_factor:.3f}, New size: {new_width}x{new_height}")
                
                # If scale factor is 1 and dimensions match, no need for canvas
                if scale_factor == 1.0 and new_width == target_width and new_height == target_height:
                    logging.info("Perfect 1:1 scale - returning original")
                    return img.copy()
                
                # Resize image
                scaled_img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                
                # Create target canvas and center the scaled image
                canvas = Image.new('RGB', (target_width, target_height), (0, 0, 0))
                x_offset = (target_width - new_width) // 2
                y_offset = (target_height - new_height) // 2
                canvas.paste(scaled_img, (x_offset, y_offset))
                
                logging.info(f"Scaled and centered: offset ({x_offset}, {y_offset})")
                return canvas
                
        except Exception as e:
            logging.error(f"Failed to scale image {image_path}: {e}")
            # Return black canvas as fallback
            return Image.new('RGB', (target_width, target_height), (0, 0, 0))
    
    async def stop(self) -> None:
        """Stop background display"""
        self.is_running = False
        logging.info("Background manager stopped")
    
    def is_active(self) -> bool:
        """Check if background display is active"""
        return self.is_running
    
    def get_status(self) -> dict:
        """Get current status information"""
        return {
            "mode": "static",
            "is_running": self.is_running,
            "background_image": self.static_background_image
        }