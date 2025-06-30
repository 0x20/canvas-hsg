"""
SplitflapDigit - Individual digit animation for splitflap display
Handles the flip animation for a single digit change
"""

import math
from typing import Optional, Tuple
from PIL import Image, ImageDraw, ImageFont


class SplitflapDigit:
    """Handles animation for a single splitflap digit"""
    
    def __init__(self, width: int, height: int, font_size: int):
        self.width = width
        self.height = height
        self.font_size = font_size
        
        # Animation properties
        self.animation_frames = 12  # Total frames for flip animation
        self.current_frame = 0
        self.is_animating = False
        
        # Digit values
        self.old_digit = "0"
        self.new_digit = "0"
        self.current_digit = "0"
        
        # Colors
        self.bg_color = (45, 45, 55)      # Dark background
        self.text_color = (255, 255, 255)  # White text
        self.shadow_color = (20, 20, 25)   # Darker shadow
        self.highlight_color = (70, 70, 80) # Light highlight
        
        # Load font
        try:
            self.font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size)
        except:
            self.font = ImageFont.load_default()
    
    def start_transition(self, new_digit: str) -> bool:
        """Start transition animation to new digit. Returns True if animation started."""
        if new_digit == self.current_digit or self.is_animating:
            return False
            
        self.old_digit = self.current_digit
        self.new_digit = new_digit
        self.current_frame = 0
        self.is_animating = True
        return True
    
    def update_animation(self) -> bool:
        """Update animation frame. Returns True if animation is complete."""
        if not self.is_animating:
            return True
            
        self.current_frame += 1
        
        if self.current_frame >= self.animation_frames:
            # Animation complete
            self.current_digit = self.new_digit
            self.is_animating = False
            return True
            
        return False
    
    def _get_animation_progress(self) -> float:
        """Get current animation progress (0.0 to 1.0)"""
        if not self.is_animating:
            return 1.0
        return self.current_frame / self.animation_frames
    
    def _ease_in_out_cubic(self, t: float) -> float:
        """Cubic easing function for smooth animation"""
        if t < 0.5:
            return 4 * t * t * t
        return 1 - pow(-2 * t + 2, 3) / 2
    
    def _draw_digit_half(self, draw: ImageDraw, digit: str, is_top: bool, y_offset: int = 0) -> None:
        """Draw half of a digit (top or bottom)"""
        # Get text dimensions
        bbox = draw.textbbox((0, 0), digit, font=self.font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        
        # Center text
        text_x = (self.width - text_width) // 2
        text_y = (self.height - text_height) // 2 + y_offset
        
        if is_top:
            # Draw top half by clipping bottom
            clip_y = self.height // 2
            for y in range(clip_y):
                for x in range(self.width):
                    # Create gradient effect
                    if y < 3:  # Top highlight
                        color = self.highlight_color
                    elif y > clip_y - 4:  # Bottom shadow for separation
                        color = self.shadow_color
                    else:
                        color = self.bg_color
                    draw.point((x, y), color)
        else:
            # Draw bottom half by clipping top
            clip_y = self.height // 2
            for y in range(clip_y, self.height):
                for x in range(self.width):
                    # Create gradient effect
                    if y > self.height - 4:  # Bottom shadow
                        color = self.shadow_color
                    elif y < clip_y + 3:  # Top highlight for separation
                        color = self.highlight_color
                    else:
                        color = self.bg_color
                    draw.point((x, y), color)
        
        # Draw text
        draw.text((text_x, text_y), digit, fill=self.text_color, font=self.font)
    
    def render(self) -> Image.Image:
        """Render current state of the digit"""
        img = Image.new('RGB', (self.width, self.height), self.bg_color)
        draw = ImageDraw.Draw(img)
        
        if not self.is_animating:
            # Static digit - just draw normally
            bbox = draw.textbbox((0, 0), self.current_digit, font=self.font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            
            text_x = (self.width - text_width) // 2
            text_y = (self.height - text_height) // 2
            
            # Draw background with subtle gradient
            for y in range(self.height):
                intensity = 45 + int(10 * (y / self.height))  # Subtle gradient
                color = (intensity, intensity, intensity + 10)
                draw.line([(0, y), (self.width, y)], fill=color)
            
            # Draw border
            draw.rectangle([0, 0, self.width-1, self.height-1], outline=self.shadow_color, width=2)
            draw.rectangle([2, 2, self.width-3, self.height-3], outline=self.highlight_color, width=1)
            
            # Draw text with shadow
            draw.text((text_x + 1, text_y + 1), self.current_digit, fill=self.shadow_color, font=self.font)
            draw.text((text_x, text_y), self.current_digit, fill=self.text_color, font=self.font)
            
        else:
            # Animation in progress - draw flip effect
            progress = self._get_animation_progress()
            eased_progress = self._ease_in_out_cubic(progress)
            
            # Calculate rotation angle (0 to 180 degrees)
            angle = eased_progress * 180
            
            if angle < 90:
                # First half - showing old digit top, new digit bottom (flipping)
                # Draw old digit top half
                self._draw_digit_half(draw, self.old_digit, True)
                
                # Draw flipping bottom half (compressed based on angle)
                scale_factor = math.cos(math.radians(angle))
                compressed_height = int(self.height * 0.5 * scale_factor)
                
                if compressed_height > 0:
                    bottom_y = self.height // 2 + (self.height // 2 - compressed_height) // 2
                    # Draw compressed old digit bottom
                    temp_img = Image.new('RGB', (self.width, self.height // 2), self.bg_color)
                    temp_draw = ImageDraw.Draw(temp_img)
                    self._draw_digit_half(temp_draw, self.old_digit, False)
                    
                    # Resize and paste
                    compressed = temp_img.resize((self.width, compressed_height), Image.Resampling.LANCZOS)
                    img.paste(compressed, (0, bottom_y))
                    
            else:
                # Second half - showing new digit top, old digit bottom (flipping)
                # Draw new digit top half
                self._draw_digit_half(draw, self.new_digit, True)
                
                # Draw flipping bottom half (expanding)
                scale_factor = abs(math.cos(math.radians(angle)))
                compressed_height = int(self.height * 0.5 * scale_factor)
                
                if compressed_height > 0:
                    bottom_y = self.height // 2 + (self.height // 2 - compressed_height) // 2
                    # Draw compressed new digit bottom
                    temp_img = Image.new('RGB', (self.width, self.height // 2), self.bg_color)
                    temp_draw = ImageDraw.Draw(temp_img)
                    self._draw_digit_half(temp_draw, self.new_digit, False)
                    
                    # Resize and paste
                    compressed = temp_img.resize((self.width, compressed_height), Image.Resampling.LANCZOS)
                    img.paste(compressed, (0, bottom_y))
            
            # Draw center line to simulate split
            center_y = self.height // 2
            draw.line([(0, center_y), (self.width, center_y)], fill=self.shadow_color, width=2)
            
            # Draw border
            draw.rectangle([0, 0, self.width-1, self.height-1], outline=self.shadow_color, width=2)
        
        return img
    
    def get_digit(self) -> str:
        """Get current displayed digit"""
        return self.current_digit
    
    def is_animation_active(self) -> bool:
        """Check if animation is currently running"""
        return self.is_animating