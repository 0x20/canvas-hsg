"""
WebcastManager - Website Casting with Auto-Scroll

Handles website casting to canvas with configurable auto-scrolling,
zoom levels, and loop management using Playwright for web automation.
"""

import asyncio
import logging
import os
import time
from dataclasses import dataclass
from typing import Optional, Dict, Any, List, Tuple
from pathlib import Path
import threading
from queue import Queue, Empty
from collections import deque

try:
    from playwright.async_api import async_playwright, Browser, Page, Playwright
except ImportError:
    logging.warning("Playwright not installed. Webcast features will be unavailable.")
    async_playwright = None


@dataclass
class WebcastConfig:
    """Configuration for webcast behavior"""
    url: str
    viewport_width: int = 1920
    viewport_height: int = 1080
    scroll_delay: float = 5.0  # seconds between scrolls
    scroll_percentage: float = 30.0  # percentage of viewport to scroll each time
    overlap_percentage: float = 5.0  # overlap between scroll positions
    loop_count: int = 3  # number of times to loop through the page
    zoom_level: float = 1.0  # browser zoom level
    wait_for_load: float = 3.0  # seconds to wait for page load
    screenshot_path: str = "/tmp/webcast_screenshot.png"
    buffer_path: str = "/tmp/webcast_buffer.png"  # buffer for next screenshot
    preload_time: float = 0.5  # seconds to wait for content to stabilize before screenshot


class WebcastManager:
    """Manages website casting with auto-scrolling functionality with buffering"""
    
    def __init__(self):
        self.playwright: Optional[Playwright] = None
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None
        self.config: Optional[WebcastConfig] = None
        self.is_running = False
        self.current_scroll_position = 0
        self.total_height = 0
        self.current_loop = 0
        self.scroll_task: Optional[asyncio.Task] = None
        
        # Screenshot cache system for instant switching
        self.screenshot_cache: List[str] = []  # Paths to all pre-captured screenshots
        self.cache_index = 0
        self.screenshots_ready = False
        self.cache_generation_task: Optional[asyncio.Task] = None
        
    async def start_webcast(self, config: WebcastConfig) -> Dict[str, Any]:
        """Start webcasting with the given configuration"""
        if async_playwright is None:
            raise RuntimeError("Playwright not available. Install with: pip install playwright && playwright install chromium")
        
        try:
            # Stop any existing webcast
            await self.stop_webcast()
            
            self.config = config
            logging.info(f"Starting webcast for URL: {config.url}")
            
            # Launch playwright
            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.launch(
                headless=True,
                args=[
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-web-security',
                    '--disable-features=VizDisplayCompositor'
                ]
            )
            
            # Create page with specified viewport
            self.page = await self.browser.new_page(
                viewport={'width': config.viewport_width, 'height': config.viewport_height}
            )
            
            # Set zoom level if specified
            if config.zoom_level != 1.0:
                await self.page.evaluate(f"document.body.style.zoom = '{config.zoom_level}'")
            
            # Navigate to URL
            await self.page.goto(config.url, wait_until='networkidle', timeout=30000)
            
            # Wait for page to load
            await asyncio.sleep(config.wait_for_load)
            
            # Get total page height
            self.total_height = await self.page.evaluate("document.documentElement.scrollHeight")
            logging.info(f"Page loaded. Total height: {self.total_height}px")
            
            # Reset scroll state
            self.current_scroll_position = 0
            self.current_loop = 0
            self.cache_index = 0
            self.is_running = True
            
            # Generate all screenshots upfront for instant switching
            logging.info("Pre-generating all screenshots for instant switching...")
            await self._generate_screenshot_cache()
            
            # Start fast display loop
            self.scroll_task = asyncio.create_task(self._fast_display_loop())
            
            return {
                "status": "started",
                "url": config.url,
                "total_height": self.total_height,
                "viewport": f"{config.viewport_width}x{config.viewport_height}",
                "screenshot_path": config.screenshot_path,
                "cache_screenshots": len(self.screenshot_cache),
                "cache_ready": self.screenshots_ready
            }
            
        except Exception as e:
            logging.error(f"Failed to start webcast: {e}")
            await self.stop_webcast()
            raise
    
    async def stop_webcast(self) -> Dict[str, Any]:
        """Stop the current webcast"""
        logging.info("Stopping webcast")
        
        self.is_running = False
        
        # Cancel tasks
        if self.scroll_task and not self.scroll_task.done():
            self.scroll_task.cancel()
            try:
                await self.scroll_task
            except asyncio.CancelledError:
                pass
        
        if self.cache_generation_task and not self.cache_generation_task.done():
            self.cache_generation_task.cancel()
            try:
                await self.cache_generation_task
            except asyncio.CancelledError:
                pass
        
        # Clean up cached screenshots
        await self._cleanup_screenshot_cache()
        
        # Close browser resources
        if self.page:
            await self.page.close()
            self.page = None
        
        if self.browser:
            await self.browser.close()
            self.browser = None
        
        if self.playwright:
            await self.playwright.stop()
            self.playwright = None
        
        return {"status": "stopped"}
    
    async def get_status(self) -> Dict[str, Any]:
        """Get current webcast status"""
        if not self.is_running:
            return {"status": "stopped"}
        
        return {
            "status": "running",
            "url": self.config.url if self.config else None,
            "current_scroll_position": self.current_scroll_position,
            "total_height": self.total_height,
            "current_loop": self.current_loop,
            "max_loops": self.config.loop_count if self.config else 0,
            "scroll_percentage": (self.cache_index / max(len(self.screenshot_cache) - 1, 1)) * 100 if self.screenshot_cache else 0,
            "screenshot_path": self.config.screenshot_path if self.config else None,
            "cache_index": self.cache_index,
            "cache_total": len(self.screenshot_cache),
            "cache_ready": self.screenshots_ready
        }
    
    async def update_config(self, new_config: Dict[str, Any]) -> Dict[str, Any]:
        """Update webcast configuration without restarting"""
        if not self.config:
            raise RuntimeError("No active webcast to update")
        
        # Update allowed fields
        if "scroll_delay" in new_config:
            self.config.scroll_delay = float(new_config["scroll_delay"])
        if "scroll_percentage" in new_config:
            self.config.scroll_percentage = float(new_config["scroll_percentage"])
        if "overlap_percentage" in new_config:
            self.config.overlap_percentage = float(new_config["overlap_percentage"])
        if "loop_count" in new_config:
            self.config.loop_count = int(new_config["loop_count"])
        
        return await self.get_status()
    
    async def _generate_screenshot_cache(self):
        """Pre-generate all screenshots for the entire page"""
        try:
            if not self.page or not self.config:
                return
            
            self.screenshot_cache = []
            
            # Calculate all scroll positions
            scroll_step = int(self.config.viewport_height * (self.config.scroll_percentage / 100))
            overlap_step = int(self.config.viewport_height * (self.config.overlap_percentage / 100))
            effective_step = scroll_step - overlap_step
            max_scroll_position = max(0, self.total_height - self.config.viewport_height)
            
            positions = []
            current_pos = 0
            position_index = 0
            
            # Generate all scroll positions
            while current_pos <= max_scroll_position:
                positions.append(current_pos)
                current_pos = min(current_pos + effective_step, max_scroll_position)
                if current_pos == max_scroll_position and len(positions) > 1:
                    break
            
            # Add final position if not already included
            if positions[-1] != max_scroll_position:
                positions.append(max_scroll_position)
            
            logging.info(f"Generating {len(positions)} screenshots...")
            
            # Create cache directory
            cache_dir = Path("/tmp/webcast_cache")
            cache_dir.mkdir(exist_ok=True)
            
            # Generate all screenshots
            for i, position in enumerate(positions):
                # Scroll to position
                await self.page.evaluate(f"window.scrollTo(0, {position})")
                
                # Wait for content to stabilize (minimal time)
                await asyncio.sleep(0.2)
                
                # Take screenshot
                screenshot_path = cache_dir / f"screenshot_{i:04d}.png"
                await self.page.screenshot(
                    path=str(screenshot_path),
                    full_page=False,
                    type='png'
                )
                
                self.screenshot_cache.append(str(screenshot_path))
                
                # Progress logging
                if i % 10 == 0 or i == len(positions) - 1:
                    logging.info(f"Generated {i+1}/{len(positions)} screenshots")
            
            # Reset to first position
            await self.page.evaluate("window.scrollTo(0, 0)")
            
            self.screenshots_ready = True
            logging.info(f"Screenshot cache ready with {len(self.screenshot_cache)} images")
            
        except Exception as e:
            logging.error(f"Failed to generate screenshot cache: {e}")
            self.screenshots_ready = False
    
    async def _fast_display_loop(self):
        """Ultra-fast display loop using pre-cached screenshots"""
        try:
            # Wait for screenshots to be ready
            while not self.screenshots_ready and self.is_running:
                await asyncio.sleep(0.1)
            
            if not self.screenshots_ready:
                logging.error("Screenshots not ready, cannot start display loop")
                return
            
            current_loop = 0
            
            while self.is_running and self.config:
                # Cycle through all cached screenshots
                for i, screenshot_path in enumerate(self.screenshot_cache):
                    if not self.is_running:
                        break
                    
                    # Copy current screenshot to display path instantly
                    if os.path.exists(screenshot_path):
                        import shutil
                        shutil.copy2(screenshot_path, self.config.screenshot_path)
                        logging.debug(f"Displaying screenshot {i+1}/{len(self.screenshot_cache)}")
                    
                    # Update tracking
                    self.cache_index = i
                    
                    # Wait for scroll delay - this is the ONLY delay now
                    await asyncio.sleep(self.config.scroll_delay)
                
                # Loop completed
                current_loop += 1
                self.current_loop = current_loop
                logging.info(f"Completed display loop {current_loop}")
                
                # Check if we should continue looping
                if self.config.loop_count > 0 and current_loop >= self.config.loop_count:
                    # Stop after specified loops (but continue if loop_count is 0 for infinite)
                    break
                    
        except asyncio.CancelledError:
            logging.info("Fast display loop cancelled")
        except Exception as e:
            logging.error(f"Error in fast display loop: {e}")
            self.is_running = False
    
    async def _cleanup_screenshot_cache(self):
        """Clean up cached screenshot files"""
        try:
            for screenshot_path in self.screenshot_cache:
                if os.path.exists(screenshot_path):
                    os.remove(screenshot_path)
            
            # Remove cache directory if empty
            cache_dir = Path("/tmp/webcast_cache")
            if cache_dir.exists() and not any(cache_dir.iterdir()):
                cache_dir.rmdir()
                
            self.screenshot_cache = []
            logging.info("Screenshot cache cleaned up")
            
        except Exception as e:
            logging.error(f"Error cleaning up screenshot cache: {e}")
    
    async def _auto_scroll_loop_buffered(self):
        """Main auto-scrolling loop with buffering"""
        try:
            while self.is_running and self.config:
                # Wait for the scroll delay, but also wait for the next position to be ready
                delay_task = asyncio.create_task(asyncio.sleep(self.config.scroll_delay))
                buffer_task = asyncio.create_task(self.buffer_ready.wait())
                
                # Wait for either the delay to complete OR the buffer to be ready
                done, pending = await asyncio.wait(
                    [delay_task, buffer_task], 
                    return_when=asyncio.FIRST_COMPLETED
                )
                
                # Cancel pending tasks
                for task in pending:
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
                
                # Check if we should continue
                if not self.is_running:
                    break
                
                # Swap the buffers - make the buffered screenshot current
                await self._swap_screenshots()
                
                # Reset events for next cycle
                self.screenshot_ready.set()
                self.buffer_ready.clear()
                
        except asyncio.CancelledError:
            logging.info("Buffered auto-scroll loop cancelled")
        except Exception as e:
            logging.error(f"Error in buffered auto-scroll loop: {e}")
            self.is_running = False
    
    async def _preload_next_position(self):
        """Background task to preload the next scroll position"""
        try:
            while self.is_running and self.config:
                # Calculate next scroll position
                next_position = self._calculate_next_scroll_position()
                
                # Move to next position in background
                if next_position != self.current_scroll_position:
                    await self.page.evaluate(f"window.scrollTo(0, {next_position})")
                    
                    # Wait for content to stabilize
                    await asyncio.sleep(self.config.preload_time)
                    
                    # Take screenshot to buffer
                    await self._take_screenshot_to_path(self.buffer_screenshot_path)
                    
                    # Update our internal position tracking
                    self.current_scroll_position = next_position
                    
                    # Signal that buffer is ready
                    self.buffer_ready.set()
                    
                    # Wait for the current screenshot to be swapped before continuing
                    await self.screenshot_ready.wait()
                    self.screenshot_ready.clear()
                else:
                    # We've reached the end, handle loop logic
                    self.current_loop += 1
                    logging.info(f"Completed loop {self.current_loop}/{self.config.loop_count}")
                    
                    if self.current_loop >= self.config.loop_count:
                        # Reset to beginning for continuous looping
                        self.current_loop = 0
                        self.current_scroll_position = 0
                        await self.page.evaluate("window.scrollTo(0, 0)")
                        logging.info("Restarting webcast from top")
                    else:
                        # Continue to next loop
                        self.current_scroll_position = 0
                        await self.page.evaluate("window.scrollTo(0, 0)")
                    
                    # Wait for content to stabilize after jump
                    await asyncio.sleep(self.config.preload_time)
                    
                    # Take screenshot to buffer
                    await self._take_screenshot_to_path(self.buffer_screenshot_path)
                    self.buffer_ready.set()
                    
                    # Wait for swap before continuing
                    await self.screenshot_ready.wait()
                    self.screenshot_ready.clear()
                
        except asyncio.CancelledError:
            logging.info("Preload task cancelled")
        except Exception as e:
            logging.error(f"Error in preload task: {e}")
            self.is_running = False
    
    def _calculate_next_scroll_position(self) -> int:
        """Calculate the next scroll position based on current settings"""
        if not self.config:
            return self.current_scroll_position
            
        # Calculate scroll step
        scroll_step = int(self.config.viewport_height * (self.config.scroll_percentage / 100))
        overlap_step = int(self.config.viewport_height * (self.config.overlap_percentage / 100))
        effective_step = scroll_step - overlap_step
        
        # Calculate next position
        max_scroll_position = max(0, self.total_height - self.config.viewport_height)
        next_position = min(
            self.current_scroll_position + effective_step,
            max_scroll_position
        )
        
        return next_position
    
    async def _swap_screenshots(self):
        """Swap the current and buffer screenshots"""
        async with self.screenshot_lock:
            if os.path.exists(self.buffer_screenshot_path):
                # Copy buffer to current (atomic operation)
                import shutil
                shutil.move(self.buffer_screenshot_path, self.current_screenshot_path)
                logging.debug("Screenshots swapped")
    
    async def _auto_scroll_loop(self):
        """Main auto-scrolling loop"""
        try:
            while self.is_running and self.config:
                # Calculate scroll step
                scroll_step = int(self.config.viewport_height * (self.config.scroll_percentage / 100))
                overlap_step = int(self.config.viewport_height * (self.config.overlap_percentage / 100))
                effective_step = scroll_step - overlap_step
                
                # Check if we've reached the end of the page
                max_scroll_position = max(0, self.total_height - self.config.viewport_height)
                
                if self.current_scroll_position >= max_scroll_position:
                    # End of page reached, check loop count
                    self.current_loop += 1
                    logging.info(f"Completed loop {self.current_loop}/{self.config.loop_count}")
                    
                    if self.current_loop >= self.config.loop_count:
                        # Reset to beginning for continuous looping
                        self.current_loop = 0
                        self.current_scroll_position = 0
                        await self.page.evaluate("window.scrollTo(0, 0)")
                        logging.info("Restarting webcast from top")
                    else:
                        # Continue to next loop
                        self.current_scroll_position = 0
                        await self.page.evaluate("window.scrollTo(0, 0)")
                else:
                    # Scroll to next position
                    self.current_scroll_position = min(
                        self.current_scroll_position + effective_step,
                        max_scroll_position
                    )
                    await self.page.evaluate(f"window.scrollTo(0, {self.current_scroll_position})")
                
                # Wait for scroll to complete and content to load
                await asyncio.sleep(0.5)
                
                # Take screenshot
                await self._take_screenshot()
                
                # Wait for configured delay
                await asyncio.sleep(self.config.scroll_delay)
                
        except asyncio.CancelledError:
            logging.info("Auto-scroll loop cancelled")
        except Exception as e:
            logging.error(f"Error in auto-scroll loop: {e}")
            self.is_running = False
    
    async def _take_screenshot_to_path(self, path: str):
        """Take a screenshot of the current page to a specific path"""
        if not self.page:
            return
        
        try:
            # Ensure directory exists
            screenshot_path = Path(path)
            screenshot_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Take screenshot
            await self.page.screenshot(
                path=path,
                full_page=False,  # Only capture viewport
                type='png'
            )
            
            logging.debug(f"Screenshot saved: {path}")
            
        except Exception as e:
            logging.error(f"Failed to take screenshot: {e}")
    
    async def _take_screenshot(self):
        """Take a screenshot of the current page (legacy method)"""
        if not self.config:
            return
        await self._take_screenshot_to_path(self.config.screenshot_path)
    
    async def manual_scroll(self, direction: str, amount: int = None) -> Dict[str, Any]:
        """Manually scroll the page"""
        if not self.page or not self.is_running:
            raise RuntimeError("No active webcast")
        
        if amount is None:
            amount = int(self.config.viewport_height * 0.1)  # 10% of viewport by default
        
        if direction == "up":
            self.current_scroll_position = max(0, self.current_scroll_position - amount)
        elif direction == "down":
            max_scroll = max(0, self.total_height - self.config.viewport_height)
            self.current_scroll_position = min(max_scroll, self.current_scroll_position + amount)
        else:
            raise ValueError("Direction must be 'up' or 'down'")
        
        await self.page.evaluate(f"window.scrollTo(0, {self.current_scroll_position})")
        await asyncio.sleep(self.config.preload_time if self.config else 0.5)
        await self._take_screenshot()
        
        return await self.get_status()
    
    async def jump_to_position(self, position_percent: float) -> Dict[str, Any]:
        """Jump to a specific position on the page"""
        if not self.page or not self.is_running:
            raise RuntimeError("No active webcast")
        
        position_percent = max(0, min(100, position_percent))
        max_scroll = max(0, self.total_height - self.config.viewport_height)
        self.current_scroll_position = int(max_scroll * (position_percent / 100))
        
        await self.page.evaluate(f"window.scrollTo(0, {self.current_scroll_position})")
        await asyncio.sleep(self.config.preload_time if self.config else 0.5)
        await self._take_screenshot()
        
        return await self.get_status()
    
    def get_current_screenshot_path(self) -> Optional[str]:
        """Get the path to the current screenshot"""
        if self.config and self.config.screenshot_path and os.path.exists(self.config.screenshot_path):
            return self.config.screenshot_path
        return None