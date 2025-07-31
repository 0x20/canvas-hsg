"""
Audio Icon Component

Renders an audio/music icon to indicate audio streaming is active.
"""

from typing import Tuple
from PIL import Image, ImageDraw
import logging

from ..layout import LayoutComponent
from ..config import BackgroundConfig


class AudioIconComponent(LayoutComponent):
    """Component for rendering an audio/music icon"""
    
    def __init__(self, size_percent: float = 0.08, component_id: str = "audio_icon"):
        super().__init__(component_id)
        self.size_percent = size_percent
    
    def calculate_size(self, canvas_width: int, canvas_height: int, 
                      config: BackgroundConfig) -> Tuple[int, int]:
        """Calculate audio icon size - small icon in corner"""
        # Make icon size based on percentage of canvas height
        icon_size = int(canvas_height * self.size_percent)
        # Minimum 32px, maximum 128px
        icon_size = max(32, min(icon_size, 128))
        return icon_size, icon_size
    
    def render(self, draw: ImageDraw.Draw, x: int, y: int, width: int, height: int,
               canvas_width: int, canvas_height: int, config: BackgroundConfig) -> None:
        """Render the audio icon at the specified position"""
        # Use the smaller of allocated width/height to keep icon square
        icon_size = min(width, height)
        
        # Calculate center position
        center_x = x + width // 2
        center_y = y + height // 2
        
        # Draw a music note icon using title color
        self._draw_music_note(draw, center_x, center_y, icon_size, config.title_color)
    
    def _draw_music_note(self, draw: ImageDraw.Draw, center_x: int, center_y: int, 
                        size: int, color: tuple) -> None:
        """Draw a stylized music note icon"""
        try:
            # Scale all measurements based on icon size
            scale = size / 64.0  # Base size of 64px
            
            # Note head (filled circle)
            head_radius = int(8 * scale)
            head_x = center_x - int(12 * scale)
            head_y = center_y + int(12 * scale)
            
            # Draw filled circle for note head
            draw.ellipse([
                head_x - head_radius, head_y - head_radius,
                head_x + head_radius, head_y + head_radius
            ], fill=color)
            
            # Note stem (vertical line)
            stem_width = max(2, int(3 * scale))
            stem_x = head_x + head_radius
            stem_top = head_y - int(32 * scale)
            stem_bottom = head_y
            
            draw.rectangle([
                stem_x, stem_top,
                stem_x + stem_width, stem_bottom
            ], fill=color)
            
            # Note flag (curved flag at top)
            flag_points = [
                (stem_x + stem_width, stem_top),
                (stem_x + stem_width + int(12 * scale), stem_top + int(6 * scale)),
                (stem_x + stem_width + int(8 * scale), stem_top + int(12 * scale)),
                (stem_x + stem_width, stem_top + int(8 * scale))
            ]
            draw.polygon(flag_points, fill=color)
            
            # Add small sound waves for audio indication
            wave_color = tuple(max(0, c - 30) for c in color)  # Slightly darker
            
            # Three curved lines representing sound waves
            for i in range(3):
                wave_offset = int((8 + i * 4) * scale)
                wave_x = center_x + int(8 * scale)
                wave_y_top = center_y - int(8 * scale) + i * int(4 * scale)
                wave_y_bottom = wave_y_top + int(8 * scale)
                
                # Draw curved wave using multiple short lines
                for j in range(8):
                    y_pos = wave_y_top + j
                    x_offset = int(wave_offset + 2 * scale * (j % 3))
                    if j < 8:
                        draw.rectangle([
                            wave_x + x_offset, y_pos,
                            wave_x + x_offset + 2, y_pos + 1
                        ], fill=wave_color)
            
        except Exception as e:
            logging.error(f"Failed to draw music note: {e}")
            # Draw a simple fallback rectangle
            fallback_size = size // 2
            draw.rectangle([
                center_x - fallback_size//2, center_y - fallback_size//2,
                center_x + fallback_size//2, center_y + fallback_size//2
            ], outline=color, fill=color)
    
    def get_min_size(self, canvas_width: int, canvas_height: int, 
                    config: BackgroundConfig) -> Tuple[int, int]:
        """Audio icon has a minimum size of 32x32"""
        return 32, 32
    
    def get_max_size(self, canvas_width: int, canvas_height: int,
                    config: BackgroundConfig) -> Tuple[int, int]:
        """Audio icon has a maximum size of 128x128"""
        return 128, 128