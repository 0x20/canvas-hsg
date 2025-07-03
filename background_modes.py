"""
Background Mode Management for HSG Canvas
Handles different background display modes including static and animated splitflap clock.
Now uses the modular background engine for flexible, configurable background generation.
"""

import asyncio
import os
import time
import logging
from enum import Enum
from pathlib import Path
from typing import Optional, Any
from PIL import Image

from splitflap import SplitflapRenderer
from background_engine import UnifiedBackgroundGenerator, BackgroundConfig


class BackgroundMode(Enum):
    """Available background display modes"""
    STATIC = "static"
    SPLITFLAP_CLOCK = "splitflap_clock"


class BackgroundManager:
    """Manages different background display modes and transitions"""
    
    def __init__(self, display_detector, framebuffer_manager):
        self.display_detector = display_detector
        self.framebuffer = framebuffer_manager
        
        # Current state
        self.current_mode = BackgroundMode.STATIC
        self.is_running = False
        self.update_task: Optional[asyncio.Task] = None
        
        # Splitflap clock renderer
        self.splitflap_renderer: Optional[SplitflapRenderer] = None
        
        # New modular background generator
        self.background_generator = UnifiedBackgroundGenerator()
        
        # Paths
        self.temp_dir = Path("/tmp/stream_images")
        self.temp_dir.mkdir(exist_ok=True)
        self.current_background_path = self.temp_dir / "current_background.png"
    
    async def set_mode(self, mode: BackgroundMode) -> bool:
        """Set background mode and start appropriate display"""
        try:
            if mode == self.current_mode and self.is_running:
                return True
            
            # Stop current mode
            await self.stop()
            
            self.current_mode = mode
            logging.info(f"Setting background mode to: {mode.value}")
            
            if mode == BackgroundMode.STATIC:
                await self._start_static_mode()
            elif mode == BackgroundMode.SPLITFLAP_CLOCK:
                await self._start_splitflap_mode()
            
            self.is_running = True
            return True
            
        except Exception as e:
            logging.error(f"Failed to set background mode to {mode.value}: {e}")
            return False
    
    async def _start_static_mode(self) -> None:
        """Start static background mode"""
        await self._create_static_background()
        await self._display_current_background()
    
    async def _start_splitflap_mode(self) -> None:
        """Start animated splitflap clock mode"""
        # Get optimal resolution
        config = self.display_detector.get_optimal_framebuffer_config()
        width, height = config['width'], config['height']
        
        # Create splitflap renderer
        self.splitflap_renderer = SplitflapRenderer(width, height)
        
        # Start update loop
        self.update_task = asyncio.create_task(self._splitflap_update_loop())
        
        # Create initial frame
        await self._update_splitflap_frame()
    
    async def _splitflap_update_loop(self) -> None:
        """Main update loop for splitflap clock animation"""
        try:
            while self.is_running and self.current_mode == BackgroundMode.SPLITFLAP_CLOCK:
                if self.splitflap_renderer:
                    # Check if clock needs update
                    needs_update = self.splitflap_renderer.update()
                    
                    if needs_update:
                        await self._update_splitflap_frame()
                
                # Update rate: 10fps during animation, 1fps when static
                if self.splitflap_renderer and self.splitflap_renderer.is_animating():
                    await asyncio.sleep(0.1)  # 10fps for smooth animation
                else:
                    await asyncio.sleep(1.0)   # 1fps for static display
                    
        except asyncio.CancelledError:
            logging.info("Splitflap update loop cancelled")
        except Exception as e:
            logging.error(f"Error in splitflap update loop: {e}")
    
    async def _update_splitflap_frame(self) -> None:
        """Generate and display current splitflap frame using the new background engine"""
        try:
            if not self.splitflap_renderer:
                return
            
            # Get optimal resolution
            display_config = self.display_detector.get_optimal_framebuffer_config()
            width, height = display_config['width'], display_config['height']
            
            # Generate splitflap background using the new engine
            frame = self.background_generator.create_splitflap_background(
                width, height, self.splitflap_renderer.clock
            )
            
            # Save to file
            frame.save(str(self.current_background_path))
            
            # Display the frame
            await self._display_current_background()
            
        except Exception as e:
            logging.error(f"Failed to update splitflap frame: {e}")
    
    async def _create_static_background(self) -> None:
        """Create static background using the new modular background engine"""
        try:
            # Get optimal resolution
            display_config = self.display_detector.get_optimal_framebuffer_config()
            width, height = display_config['width'], display_config['height']
            
            # Generate background using the new engine
            img = self.background_generator.create_static_background(width, height)
            
            # Save static background
            img.save(str(self.current_background_path))
            logging.info(f"Created static background: {width}x{height}")
            
        except Exception as e:
            logging.error(f"Failed to create static background: {e}")
            raise
    
    async def _display_current_background(self) -> None:
        """Display the current background image using available viewers"""
        try:
            if not self.current_background_path.exists():
                logging.warning("No background image to display")
                return
            
            # Use framebuffer if available
            if self.framebuffer and self.framebuffer.is_available:
                success = self.framebuffer.display_image(str(self.current_background_path))
                if not success:
                    logging.warning("Framebuffer display failed, trying image viewers")
                    await self._display_with_image_viewer()
            else:
                # Fallback to image viewers
                await self._display_with_image_viewer()
                
        except Exception as e:
            logging.error(f"Failed to display background: {e}")
    
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
    
    async def stop(self) -> None:
        """Stop current background mode"""
        self.is_running = False
        
        if self.update_task:
            self.update_task.cancel()
            try:
                await self.update_task
            except asyncio.CancelledError:
                pass
            self.update_task = None
        
        self.splitflap_renderer = None
        logging.info("Background manager stopped")
    
    def get_current_mode(self) -> BackgroundMode:
        """Get current background mode"""
        return self.current_mode
    
    def get_status(self) -> dict:
        """Get current status information"""
        status = {
            "mode": self.current_mode.value,
            "is_running": self.is_running,
            "has_update_task": self.update_task is not None
        }
        
        if self.current_mode == BackgroundMode.SPLITFLAP_CLOCK and self.splitflap_renderer:
            status.update({
                "current_time": self.splitflap_renderer.get_current_time(),
                "is_animating": self.splitflap_renderer.is_animating()
            })
        
        return status