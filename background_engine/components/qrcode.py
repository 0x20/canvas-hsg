"""
QR Code Component

Renders QR codes with configurable content, size, and styling.
"""

from typing import Tuple, Optional
from PIL import Image, ImageDraw
import qrcode
import logging

from ..layout import LayoutComponent
from ..config import BackgroundConfig


class QRCodeComponent(LayoutComponent):
    """Component for rendering QR codes"""
    
    def __init__(self, content: str = None, size_percent: float = None,
                 box_size_scale: float = None, component_id: str = "qrcode"):
        super().__init__(component_id)
        self.content = content
        self.size_percent = size_percent
        self.box_size_scale = box_size_scale
        self._qr_cache = {}
    
    def _get_content(self, config: BackgroundConfig) -> str:
        """Get QR content, using config server URL if not specified"""
        return self.content if self.content is not None else config.get_server_url()
    
    def _get_size_percent(self, config: BackgroundConfig) -> float:
        """Get size percentage, using config default if not specified"""
        return self.size_percent if self.size_percent is not None else config.qr_size_percent
    
    def _get_box_size_scale(self, config: BackgroundConfig) -> float:
        """Get box size scale, using config default if not specified"""
        return self.box_size_scale if self.box_size_scale is not None else config.qr_box_size_scale
    
    def _create_qr_code(self, content: str, target_size: int, config: BackgroundConfig) -> Image.Image:
        """Create QR code image with caching"""
        cache_key = (content, target_size, self._get_box_size_scale(config))
        
        if cache_key not in self._qr_cache:
            try:
                # Calculate appropriate box size for target size
                # Start with a reasonable base and scale it
                font_scale = config.calculate_font_scale(target_size * 10, target_size * 10)
                base_box_size = max(5, int(8 * font_scale * self._get_box_size_scale(config)))
                
                qr = qrcode.QRCode(
                    version=1,
                    error_correction=qrcode.constants.ERROR_CORRECT_L,
                    box_size=base_box_size,
                    border=config.qr_border,
                )
                qr.add_data(content)
                qr.make(fit=True)
                
                # Create QR image
                qr_bg_color = config.get_qr_background_color()
                qr_img = qr.make_image(
                    fill_color=config.qr_foreground_color,
                    back_color=qr_bg_color
                )
                
                # Resize to target size
                qr_resized = qr_img.resize((target_size, target_size), Image.Resampling.NEAREST)
                self._qr_cache[cache_key] = qr_resized
                
            except Exception as e:
                logging.error(f"Failed to create QR code: {e}")
                # Create a placeholder image
                placeholder = Image.new('RGB', (target_size, target_size), (100, 100, 100))
                self._qr_cache[cache_key] = placeholder
        
        return self._qr_cache[cache_key]
    
    def calculate_size(self, canvas_width: int, canvas_height: int, 
                      config: BackgroundConfig) -> Tuple[int, int]:
        """Calculate QR code size based on configuration - 30% of canvas height"""
        size_percent = self._get_size_percent(config)
        
        # Calculate size as percentage of canvas height (30%)
        qr_size = int(canvas_height * size_percent)
        
        return qr_size, qr_size
    
    def render(self, draw: ImageDraw.Draw, x: int, y: int, width: int, height: int,
               canvas_width: int, canvas_height: int, config: BackgroundConfig) -> None:
        """Render the QR code at the specified position"""
        content = self._get_content(config)
        
        # Use the smaller of allocated width/height to keep QR square
        qr_size = min(width, height)
        
        # Generate QR code
        qr_img = self._create_qr_code(content, qr_size, config)
        
        # Calculate position to center QR within allocated area
        qr_x = x + (width - qr_size) // 2
        qr_y = y + (height - qr_size) // 2
        
        # Convert PIL Image to paste onto the draw target
        # We need to get the underlying image from the draw object
        # This is a bit tricky with PIL ImageDraw, so we'll use a different approach
        
        # Since we can't directly paste onto ImageDraw, we'll draw the QR manually
        # by getting the pixel data and drawing rectangles
        self._draw_qr_manually(draw, qr_img, qr_x, qr_y)
    
    def _draw_qr_manually(self, draw: ImageDraw.Draw, qr_img: Image.Image, x: int, y: int) -> None:
        """Draw QR code manually by examining pixels and drawing rectangles"""
        try:
            # Convert QR image to RGB if needed
            if qr_img.mode != 'RGB':
                qr_img = qr_img.convert('RGB')
            
            width, height = qr_img.size
            
            # Sample the QR image and draw rectangles for dark pixels
            # This is less efficient but works with ImageDraw
            
            # Get the background and foreground colors by sampling corners
            bg_color = qr_img.getpixel((0, 0))
            
            # Draw the QR by examining each pixel
            for py in range(height):
                for px in range(width):
                    pixel_color = qr_img.getpixel((px, py))
                    
                    # If pixel is not background color, draw it
                    if pixel_color != bg_color:
                        draw.rectangle([
                            x + px, y + py,
                            x + px + 1, y + py + 1
                        ], fill=pixel_color)
        
        except Exception as e:
            logging.error(f"Failed to draw QR code manually: {e}")
            # Draw a placeholder rectangle
            draw.rectangle([x, y, x + qr_img.width, y + qr_img.height], 
                         outline=(255, 255, 255), width=2)
    
    def get_min_size(self, canvas_width: int, canvas_height: int, 
                    config: BackgroundConfig) -> Tuple[int, int]:
        """QR code has a minimum readable size"""
        min_size = 50  # Minimum readable QR size
        return min_size, min_size
    
    def get_max_size(self, canvas_width: int, canvas_height: int,
                    config: BackgroundConfig) -> Tuple[int, int]:
        """QR code max size is constrained by configuration percentage"""
        size_percent = self._get_size_percent(config)
        max_size = int(canvas_height * size_percent)
        return max_size, max_size