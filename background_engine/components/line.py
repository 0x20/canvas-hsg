"""
Line Component

Renders decorative horizontal lines with configurable width, height, and color.
"""

from typing import Tuple, Optional
from PIL import ImageDraw

from ..layout import LayoutComponent
from ..config import BackgroundConfig


class LineComponent(LayoutComponent):
    """Component for rendering decorative horizontal lines"""
    
    def __init__(self, width_percent: float = None, height_px: int = None,
                 color: Tuple[int, int, int] = None, component_id: str = "line"):
        super().__init__(component_id)
        self.width_percent = width_percent
        self.height_px = height_px
        self.color = color
    
    def _get_width_percent(self, config: BackgroundConfig) -> float:
        """Get width percentage, using config default if not specified"""
        return self.width_percent if self.width_percent is not None else config.line_width_percent
    
    def _get_height_px(self, config: BackgroundConfig) -> int:
        """Get height in pixels, using config default if not specified"""
        if self.height_px is not None:
            return self.height_px
        
        # Use specific line height based on component ID
        if self.component_id == "upper_line":
            return config.upper_line_height_px
        elif self.component_id == "lower_line":
            return config.lower_line_height_px
        else:
            return config.line_height_px
    
    def _get_color(self, config: BackgroundConfig) -> Tuple[int, int, int]:
        """Get color, using config default if not specified"""
        return self.color if self.color is not None else config.line_color
    
    def calculate_size(self, canvas_width: int, canvas_height: int, 
                      config: BackgroundConfig) -> Tuple[int, int]:
        """Calculate line size based on configuration"""
        width_percent = self._get_width_percent(config)
        height_px = self._get_height_px(config)
        
        # Calculate width as percentage of canvas width
        line_width = int(canvas_width * width_percent)
        
        # Height is fixed in pixels
        line_height = height_px
        
        return line_width, line_height
    
    def render(self, draw: ImageDraw.Draw, x: int, y: int, width: int, height: int,
               canvas_width: int, canvas_height: int, config: BackgroundConfig) -> None:
        """Render the line at the specified position"""
        color = self._get_color(config)
        
        # Only render if line has positive dimensions
        if width > 0 and height > 0:
            # Center the line horizontally within allocated area
            line_width = min(width, int(canvas_width * self._get_width_percent(config)))
            line_x = x + (width - line_width) // 2
            
            # Center the line vertically within allocated area
            line_height = min(height, self._get_height_px(config))
            line_y = y + (height - line_height) // 2
            
            # Draw rectangle
            draw.rectangle([
                line_x,
                line_y,
                line_x + line_width,
                line_y + line_height
            ], fill=color)
    
    def get_min_size(self, canvas_width: int, canvas_height: int, 
                    config: BackgroundConfig) -> Tuple[int, int]:
        """Line has minimum size of 1 pixel"""
        width_percent = self._get_width_percent(config)
        height_px = self._get_height_px(config)
        
        # Minimum width is 1 pixel, unless width_percent is 0 (hidden line)
        min_width = 1 if width_percent > 0 else 0
        min_height = max(1, height_px) if width_percent > 0 else 0
        
        return min_width, min_height
    
    def get_max_size(self, canvas_width: int, canvas_height: int,
                    config: BackgroundConfig) -> Tuple[int, int]:
        """Line width is constrained by percentage, height by pixels"""
        width_percent = self._get_width_percent(config)
        height_px = self._get_height_px(config)
        
        max_width = int(canvas_width * width_percent)
        max_height = height_px
        
        return max_width, max_height