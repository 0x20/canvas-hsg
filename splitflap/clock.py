"""
SplitflapClock - Coordinates 4-digit HH:MM splitflap display
Manages time detection, transition triggering, and multi-digit animations
"""

import time
from datetime import datetime
from typing import List, Tuple, Optional
from PIL import Image

from .digit import SplitflapDigit


class SplitflapClock:
    """Manages a 4-digit HH:MM splitflap clock display"""
    
    def __init__(self, digit_width: int, digit_height: int, font_size: int, spacing: int = 10):
        self.digit_width = digit_width
        self.digit_height = digit_height
        self.spacing = spacing
        
        # Create 4 digits: HH:MM
        self.digits = [
            SplitflapDigit(digit_width, digit_height, font_size),  # Hour tens
            SplitflapDigit(digit_width, digit_height, font_size),  # Hour ones
            SplitflapDigit(digit_width, digit_height, font_size),  # Minute tens
            SplitflapDigit(digit_width, digit_height, font_size),  # Minute ones
        ]
        
        # Time tracking
        self.current_time = None
        self.last_update_time = 0
        
        # Calculate total width for centering
        self.total_width = (4 * digit_width) + (3 * spacing) + (2 * spacing)  # Extra space for colon
        
        # Initialize with current time
        self._update_time_display()
    
    def _update_time_display(self) -> None:
        """Update all digits to show current time without animation"""
        now = datetime.now()
        time_str = now.strftime("%H%M")  # HHMM format
        
        for i, digit_char in enumerate(time_str):
            self.digits[i].current_digit = digit_char
            self.digits[i].old_digit = digit_char
            self.digits[i].new_digit = digit_char
        
        self.current_time = time_str
    
    def _get_time_string(self) -> str:
        """Get current time as HHMM string"""
        return datetime.now().strftime("%H%M")
    
    def update(self) -> bool:
        """Check for time changes and update animations. Returns True if display needs refresh."""
        now = time.time()
        
        # Throttle updates to avoid excessive checking
        if now - self.last_update_time < 0.1:  # Update at most 10 times per second
            return self._update_animations()
        
        self.last_update_time = now
        
        # Check if time has changed
        current_time_str = self._get_time_string()
        needs_refresh = False
        
        if current_time_str != self.current_time:
            # Time changed - trigger transitions for changed digits
            old_time = self.current_time or "0000"
            
            for i, (old_digit, new_digit) in enumerate(zip(old_time, current_time_str)):
                if old_digit != new_digit:
                    # Add small delay between digit transitions for cascade effect
                    if self.digits[i].start_transition(new_digit):
                        needs_refresh = True
            
            self.current_time = current_time_str
        
        # Update any ongoing animations
        animation_active = self._update_animations()
        
        return needs_refresh or animation_active
    
    def _update_animations(self) -> bool:
        """Update all digit animations. Returns True if any animation is active."""
        animation_active = False
        
        for digit in self.digits:
            if digit.is_animation_active():
                digit.update_animation()
                animation_active = True
        
        return animation_active
    
    def get_display_size(self) -> Tuple[int, int]:
        """Get the total size needed for the clock display"""
        return (self.total_width, self.digit_height)
    
    def render(self, background_color: Tuple[int, int, int] = (20, 20, 30)) -> Image.Image:
        """Render the complete 4-digit clock with colon separator"""
        
        # Create canvas
        img = Image.new('RGB', (self.total_width, self.digit_height), background_color)
        
        # Calculate starting position to center the clock
        current_x = 0
        
        # Render each digit with spacing
        for i, digit in enumerate(self.digits):
            digit_img = digit.render()
            img.paste(digit_img, (current_x, 0))
            current_x += self.digit_width
            
            # Add colon after hour digits (between index 1 and 2)
            if i == 1:
                current_x += self.spacing
                self._draw_colon(img, current_x, background_color)
                current_x += self.spacing
            elif i < 3:  # Add normal spacing between other digits
                current_x += self.spacing
        
        return img
    
    def _draw_colon(self, img: Image.Image, x: int, bg_color: Tuple[int, int, int]) -> None:
        """Draw colon separator between hours and minutes"""
        from PIL import ImageDraw
        
        draw = ImageDraw.Draw(img)
        
        # Colon properties
        dot_size = max(3, self.digit_width // 15)
        colon_width = dot_size * 2
        
        # Position dots vertically
        center_y = self.digit_height // 2
        upper_dot_y = center_y - self.digit_height // 4
        lower_dot_y = center_y + self.digit_height // 4
        
        dot_x = x + (self.spacing - colon_width) // 2
        
        # Draw upper dot
        draw.ellipse([
            dot_x, upper_dot_y - dot_size,
            dot_x + colon_width, upper_dot_y + dot_size
        ], fill=(255, 255, 255))
        
        # Draw lower dot
        draw.ellipse([
            dot_x, lower_dot_y - dot_size,
            dot_x + colon_width, lower_dot_y + dot_size
        ], fill=(255, 255, 255))
    
    def get_current_time_string(self) -> str:
        """Get current displayed time as HH:MM string"""
        if not self.current_time:
            return "00:00"
        return f"{self.current_time[:2]}:{self.current_time[2:]}"
    
    def is_any_animation_active(self) -> bool:
        """Check if any digit is currently animating"""
        return any(digit.is_animation_active() for digit in self.digits)
    
    def force_update(self) -> None:
        """Force immediate update to current time (useful for initialization)"""
        self._update_time_display()
    
    def get_animation_progress(self) -> float:
        """Get overall animation progress (0.0 to 1.0), 1.0 if no animation"""
        active_digits = [d for d in self.digits if d.is_animation_active()]
        if not active_digits:
            return 1.0
        
        # Return average progress of animating digits
        total_progress = sum(d._get_animation_progress() for d in active_digits)
        return total_progress / len(active_digits)