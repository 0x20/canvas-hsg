"""
Clock Component

Renders splitflap-style clock displays with configurable size and scaling.
"""

from typing import Tuple, Optional, TYPE_CHECKING
from PIL import Image, ImageDraw

from ..layout import LayoutComponent
from ..config import BackgroundConfig

if TYPE_CHECKING:
    from ...splitflap.clock import SplitflapClock


class ClockComponent(LayoutComponent):
    """Component for rendering splitflap clocks"""
    
    def __init__(self, splitflap_clock: 'SplitflapClock', 
                 size_scale: float = None, component_id: str = "clock"):
        super().__init__(component_id)
        self.splitflap_clock = splitflap_clock
        self.size_scale = size_scale
    
    def _get_size_scale(self, config: BackgroundConfig) -> float:
        """Get size scale, using config default if not specified"""
        return self.size_scale if self.size_scale is not None else 1.0
    
    def calculate_size(self, canvas_width: int, canvas_height: int, 
                      config: BackgroundConfig) -> Tuple[int, int]:
        """Calculate clock size based on splitflap clock dimensions and scaling"""
        size_scale = self._get_size_scale(config)
        
        # Get the splitflap clock's natural display size
        clock_width, clock_height = self.splitflap_clock.get_display_size()
        
        # Apply configuration scaling
        font_scale = config.calculate_font_scale(canvas_width, canvas_height)
        total_scale = size_scale * font_scale
        
        # Scale the clock dimensions
        scaled_width = int(clock_width * total_scale)
        scaled_height = int(clock_height * total_scale)
        
        return scaled_width, scaled_height
    
    def render(self, draw: ImageDraw.Draw, x: int, y: int, width: int, height: int,
               canvas_width: int, canvas_height: int, config: BackgroundConfig) -> None:
        """Render the splitflap clock at the specified position"""
        
        # Get the clock's current rendered image
        clock_img = self.splitflap_clock.render(config.background_color)
        
        # Calculate scaling to fit within allocated area
        clock_width, clock_height = clock_img.size
        scale_x = width / clock_width if clock_width > 0 else 1.0
        scale_y = height / clock_height if clock_height > 0 else 1.0
        scale = min(scale_x, scale_y)  # Maintain aspect ratio
        
        # Calculate new size
        new_width = int(clock_width * scale)
        new_height = int(clock_height * scale)
        
        # Resize clock image if needed
        if scale != 1.0:
            clock_img = clock_img.resize((new_width, new_height), Image.Resampling.LANCZOS)
        
        # Calculate position to center clock within allocated area
        clock_x = x + (width - new_width) // 2
        clock_y = y + (height - new_height) // 2
        
        # Draw clock manually by examining pixels
        self._draw_clock_manually(draw, clock_img, clock_x, clock_y)
    
    def _draw_clock_manually(self, draw: ImageDraw.Draw, clock_img: Image.Image, x: int, y: int) -> None:
        """Draw clock manually by examining pixels and drawing rectangles"""
        try:
            # Convert clock image to RGB if needed
            if clock_img.mode != 'RGB':
                clock_img = clock_img.convert('RGB')
            
            width, height = clock_img.size
            
            # Draw the clock by examining each pixel
            for py in range(height):
                for px in range(width):
                    pixel_color = clock_img.getpixel((px, py))
                    
                    # Draw pixel as a small rectangle
                    draw.rectangle([
                        x + px, y + py,
                        x + px + 1, y + py + 1
                    ], fill=pixel_color)
        
        except Exception as e:
            import logging
            logging.error(f"Failed to draw clock manually: {e}")
            # Draw a placeholder rectangle
            draw.rectangle([x, y, x + clock_img.width, y + clock_img.height], 
                         outline=(255, 255, 255), width=2)
            
            # Draw clock placeholder text
            try:
                from PIL import ImageFont
                font = ImageFont.load_default()
                time_str = self.splitflap_clock.get_current_time_string()
                text_bbox = font.getbbox(time_str)
                text_width = text_bbox[2] - text_bbox[0]
                text_height = text_bbox[3] - text_bbox[1]
                text_x = x + (clock_img.width - text_width) // 2
                text_y = y + (clock_img.height - text_height) // 2
                draw.text((text_x, text_y), time_str, fill=(255, 255, 255), font=font)
            except:
                pass  # Fallback failed, just show the rectangle
    
    def get_min_size(self, canvas_width: int, canvas_height: int, 
                    config: BackgroundConfig) -> Tuple[int, int]:
        """Clock has a minimum readable size"""
        # Get the splitflap clock's natural size as minimum
        min_width, min_height = self.splitflap_clock.get_display_size()
        
        # Apply a minimum scale factor
        min_scale = 0.3  # Don't allow clock to be smaller than 30% of original
        min_width = int(min_width * min_scale)
        min_height = int(min_height * min_scale)
        
        return min_width, min_height
    
    def update(self) -> bool:
        """Update the clock and return True if display needs refresh"""
        return self.splitflap_clock.update()
    
    def is_animating(self) -> bool:
        """Check if clock is currently animating"""
        return self.splitflap_clock.is_any_animation_active()
    
    def get_current_time(self) -> str:
        """Get current displayed time"""
        return self.splitflap_clock.get_current_time_string()
    
    def force_time_update(self) -> None:
        """Force clock to update to current time"""
        self.splitflap_clock.force_update()