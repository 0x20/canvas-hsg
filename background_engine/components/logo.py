"""
Logo Component

Renders logo images with configurable size and scaling.
"""

from typing import Tuple, Optional
from PIL import Image, ImageDraw
import logging
import os

from ..layout import LayoutComponent
from ..config import BackgroundConfig


class LogoComponent(LayoutComponent):
    """Component for rendering logo images"""
    
    def __init__(self, image_path: str = None, size_percent: float = None,
                 min_size: int = None, max_size: int = None, component_id: str = "logo"):
        super().__init__(component_id)
        self.image_path = image_path
        self.size_percent = size_percent
        self.min_size = min_size
        self.max_size = max_size
        self._image_cache = {}
    
    def _get_image_path(self, config: BackgroundConfig) -> str:
        """Get image path, using config default if not specified"""
        return self.image_path if self.image_path is not None else config.logo_path
    
    def _get_size_percent(self, config: BackgroundConfig) -> float:
        """Get size percentage, using config default if not specified"""
        return self.size_percent if self.size_percent is not None else config.logo_size_percent
    
    def _get_min_size(self, config: BackgroundConfig) -> int:
        """Get minimum size, using config default if not specified"""
        return self.min_size if self.min_size is not None else config.logo_min_size
    
    def _get_max_size(self, config: BackgroundConfig) -> int:
        """Get maximum size, using config default if not specified"""
        return self.max_size if self.max_size is not None else config.logo_max_size
    
    def _load_logo_image(self, image_path: str, target_size: int) -> Optional[Image.Image]:
        """Load and resize logo image with caching"""
        cache_key = (image_path, target_size)
        
        if cache_key not in self._image_cache:
            try:
                if not os.path.exists(image_path):
                    logging.warning(f"Logo image not found: {image_path}")
                    self._image_cache[cache_key] = None
                    return None
                
                # Load image
                logo_img = Image.open(image_path)
                
                # Resize to target size while maintaining aspect ratio
                logo_resized = logo_img.resize((target_size, target_size), Image.Resampling.LANCZOS)
                
                self._image_cache[cache_key] = logo_resized
                
            except Exception as e:
                logging.error(f"Failed to load logo image {image_path}: {e}")
                self._image_cache[cache_key] = None
        
        return self._image_cache[cache_key]
    
    def calculate_size(self, canvas_width: int, canvas_height: int, 
                      config: BackgroundConfig) -> Tuple[int, int]:
        """Calculate logo size based on configuration"""
        size_percent = self._get_size_percent(config)
        min_size = self._get_min_size(config)
        max_size = self._get_max_size(config)
        
        # Calculate size as percentage of smaller canvas dimension
        smaller_dimension = min(canvas_width, canvas_height)
        logo_size = int(smaller_dimension * size_percent)
        
        # Apply min/max constraints
        logo_size = max(min_size, min(logo_size, max_size))
        
        return logo_size, logo_size
    
    def render(self, draw: ImageDraw.Draw, x: int, y: int, width: int, height: int,
               canvas_width: int, canvas_height: int, config: BackgroundConfig) -> None:
        """Render the logo at the specified position"""
        image_path = self._get_image_path(config)
        
        # Use the smaller of allocated width/height to keep logo square
        logo_size = min(width, height)
        
        # Load logo image
        logo_img = self._load_logo_image(image_path, logo_size)
        
        if logo_img is None:
            # Draw a placeholder if logo couldn't be loaded
            placeholder_color = (100, 100, 100)
            placeholder_size = logo_size // 2
            placeholder_x = x + (width - placeholder_size) // 2
            placeholder_y = y + (height - placeholder_size) // 2
            
            draw.rectangle([
                placeholder_x, placeholder_y,
                placeholder_x + placeholder_size, placeholder_y + placeholder_size
            ], outline=placeholder_color, width=2)
            
            # Draw an X to indicate missing image
            draw.line([
                placeholder_x, placeholder_y,
                placeholder_x + placeholder_size, placeholder_y + placeholder_size
            ], fill=placeholder_color, width=2)
            draw.line([
                placeholder_x + placeholder_size, placeholder_y,
                placeholder_x, placeholder_y + placeholder_size
            ], fill=placeholder_color, width=2)
            
            return
        
        # Calculate position to center logo within allocated area
        logo_x = x + (width - logo_size) // 2
        logo_y = y + (height - logo_size) // 2
        
        # Draw logo manually by examining pixels (similar to QR code approach)
        self._draw_logo_manually(draw, logo_img, logo_x, logo_y)
    
    def _draw_logo_manually(self, draw: ImageDraw.Draw, logo_img: Image.Image, x: int, y: int) -> None:
        """Draw logo manually by examining pixels and drawing rectangles"""
        try:
            # Convert logo image to RGBA to handle transparency
            if logo_img.mode not in ('RGBA', 'LA'):
                if logo_img.mode == 'P' and 'transparency' in logo_img.info:
                    logo_img = logo_img.convert('RGBA')
                else:
                    logo_img = logo_img.convert('RGB')
            
            width, height = logo_img.size
            
            # Draw the logo by examining each pixel
            for py in range(height):
                for px in range(width):
                    pixel = logo_img.getpixel((px, py))
                    
                    # Handle transparency
                    if logo_img.mode in ('RGBA', 'LA'):
                        if len(pixel) >= 4 and pixel[3] == 0:  # Transparent pixel
                            continue
                        # Use RGB components only
                        pixel_color = pixel[:3]
                    else:
                        pixel_color = pixel
                    
                    # Draw pixel as a small rectangle
                    draw.rectangle([
                        x + px, y + py,
                        x + px + 1, y + py + 1
                    ], fill=pixel_color)
        
        except Exception as e:
            logging.error(f"Failed to draw logo manually: {e}")
            # Draw a placeholder rectangle
            draw.rectangle([x, y, x + logo_img.width, y + logo_img.height], 
                         outline=(255, 255, 255), width=2)
    
    def get_min_size(self, canvas_width: int, canvas_height: int, 
                    config: BackgroundConfig) -> Tuple[int, int]:
        """Logo has a configurable minimum size"""
        min_size = self._get_min_size(config)
        return min_size, min_size
    
    def get_max_size(self, canvas_width: int, canvas_height: int,
                    config: BackgroundConfig) -> Tuple[int, int]:
        """Logo has a configurable maximum size"""
        max_size = self._get_max_size(config)
        return max_size, max_size