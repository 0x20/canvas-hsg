"""
Title Component

Renders a title text with optional glow effect and configurable styling.
"""

from typing import Tuple
from PIL import ImageFont, ImageDraw
import logging

from ..layout import LayoutComponent
from ..config import BackgroundConfig


class TitleComponent(LayoutComponent):
    """Component for rendering the main title text"""
    
    def __init__(self, text: str = None, font_scale: float = None, 
                 color: Tuple[int, int, int] = None, glow_enabled: bool = None,
                 component_id: str = "title"):
        super().__init__(component_id)
        self.text = text
        self.font_scale = font_scale
        self.color = color
        self.glow_enabled = glow_enabled
        self._font_cache = {}
    
    def _get_text(self, config: BackgroundConfig) -> str:
        """Get text, using config default if not specified"""
        return self.text if self.text is not None else config.title_text
    
    def _get_color(self, config: BackgroundConfig) -> Tuple[int, int, int]:
        """Get color, using config default if not specified"""
        return self.color if self.color is not None else config.title_color
    
    def _get_glow_enabled(self, config: BackgroundConfig) -> bool:
        """Get glow setting, using config default if not specified"""
        return self.glow_enabled if self.glow_enabled is not None else config.title_glow_enabled
    
    def _get_font_scale(self, config: BackgroundConfig) -> float:
        """Get font scale, using config default if not specified"""
        return self.font_scale if self.font_scale is not None else config.title_font_scale
    
    def _load_font(self, size: int, config: BackgroundConfig) -> ImageFont.ImageFont:
        """Load font with caching"""
        cache_key = (config.title_font_path, size)
        
        if cache_key not in self._font_cache:
            try:
                font = ImageFont.truetype(config.title_font_path, size)
                self._font_cache[cache_key] = font
            except Exception as e:
                if config.fallback_to_default_font:
                    logging.warning(f"Could not load title font {config.title_font_path}: {e}, using default")
                    font = ImageFont.load_default()
                    self._font_cache[cache_key] = font
                else:
                    raise e
        
        return self._font_cache[cache_key]
    
    def calculate_size(self, canvas_width: int, canvas_height: int, 
                      config: BackgroundConfig) -> Tuple[int, int]:
        """Calculate title size based on text and font"""
        text = self._get_text(config)
        font_scale = self._get_font_scale(config)
        
        # Calculate font size
        font_size = config.get_title_font_size(canvas_width, canvas_height)
        font_size = int(font_size * font_scale)
        
        # Load font and measure text
        font = self._load_font(font_size, config)
        
        # Use textbbox for accurate measurement
        bbox = font.getbbox(text)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        
        # Add padding for glow effect if enabled
        if self._get_glow_enabled(config):
            glow_offset = max(1, int(font_size * config.title_glow_offset))
            text_width += 2 * glow_offset
            text_height += 2 * glow_offset
        
        return text_width, text_height
    
    def render(self, draw: ImageDraw.Draw, x: int, y: int, width: int, height: int,
               canvas_width: int, canvas_height: int, config: BackgroundConfig) -> None:
        """Render the title at the specified position"""
        text = self._get_text(config)
        color = self._get_color(config)
        glow_enabled = self._get_glow_enabled(config)
        font_scale = self._get_font_scale(config)
        
        # Calculate font size
        font_size = config.get_title_font_size(canvas_width, canvas_height)
        font_size = int(font_size * font_scale)
        
        # Load font
        font = self._load_font(font_size, config)
        
        # Calculate text position within allocated area
        bbox = font.getbbox(text)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        
        # Center text within allocated area
        text_x = x + (width - text_width) // 2
        text_y = y + (height - text_height) // 2
        
        # Adjust for glow offset if enabled
        if glow_enabled:
            glow_offset = max(1, int(font_size * config.title_glow_offset))
            text_x += glow_offset
            text_y += glow_offset
            
            # Draw glow effect
            glow_color = config.title_glow_color
            for offset in [(glow_offset, glow_offset), (-glow_offset, glow_offset),
                          (glow_offset, -glow_offset), (-glow_offset, -glow_offset)]:
                draw.text((text_x + offset[0], text_y + offset[1]), 
                         text, fill=glow_color, font=font)
        
        # Draw main text
        draw.text((text_x, text_y), text, fill=color, font=font)
    
    def get_min_size(self, canvas_width: int, canvas_height: int, 
                    config: BackgroundConfig) -> Tuple[int, int]:
        """Title has a minimum readable size"""
        min_font_size = 20  # Minimum readable font size
        font = self._load_font(min_font_size, config)
        
        text = self._get_text(config)
        bbox = font.getbbox(text)
        return bbox[2] - bbox[0], bbox[3] - bbox[1]