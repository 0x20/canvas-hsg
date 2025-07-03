"""
SplitflapRenderer - Combines splitflap clock with background elements
Handles composition of clock with title, QR code, and decorative elements
"""

import os
import asyncio
import time
from datetime import datetime
from pathlib import Path
from typing import Tuple, Optional
from PIL import Image, ImageDraw, ImageFont
import qrcode

from .clock import SplitflapClock


class SplitflapRenderer:
    """Renders complete splitflap clock background with all elements"""
    
    def __init__(self, width: int, height: int):
        self.width = width
        self.height = height
        
        # Calculate responsive sizing
        self.font_scale = min(width / 1920, height / 1080)
        self.title_font_size = int(80 * self.font_scale)
        self.subtitle_font_size = int(40 * self.font_scale)
        
        # Clock sizing
        self.clock_digit_width = int(120 * self.font_scale)
        self.clock_digit_height = int(160 * self.font_scale)
        self.clock_font_size = int(100 * self.font_scale)
        self.clock_spacing = int(15 * self.font_scale)
        
        # Create splitflap clock
        self.clock = SplitflapClock(
            self.clock_digit_width,
            self.clock_digit_height,
            self.clock_font_size,
            self.clock_spacing
        )
        
        # Colors
        self.bg_color = (20, 20, 30)
        self.title_color = (100, 150, 255)
        self.subtitle_color = (180, 180, 180)
        self.accent_color = (100, 150, 255)
        
        # Load fonts
        try:
            self.title_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", self.title_font_size)
            self.subtitle_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", self.subtitle_font_size)
        except:
            self.title_font = ImageFont.load_default()
            self.subtitle_font = ImageFont.load_default()
        
        # Cache for static elements
        self._background_template = None
        self._qr_image = None
        
        # Layout positions (calculated once)
        self._calculate_layout()
    
    def _calculate_layout(self) -> None:
        """Calculate positions using design principles (rule of thirds & golden ratio)"""
        temp_img = Image.new('RGB', (100, 100), self.bg_color)
        temp_draw = ImageDraw.Draw(temp_img)
        
        # Design-based layout calculations
        golden_upper = int(self.height * 0.382)  # Golden ratio upper point
        golden_lower = int(self.height * 0.618)  # Golden ratio lower point
        third_upper = int(self.height / 3)       # Rule of thirds upper
        third_lower = int(self.height * 2 / 3)   # Rule of thirds lower
        
        # Title positioning - upper area with margin
        title = "Hackerspace.gent Canvas"
        bbox = temp_draw.textbbox((0, 0), title, font=self.title_font)
        title_width = bbox[2] - bbox[0]
        self.title_x = (self.width - title_width) // 2
        self.title_y = max(int(self.height * 0.12), int(third_upper * 0.6))  # 12% from top or 60% of upper third
        
        # Clock positioning - between title and golden upper point
        clock_width, clock_height = self.clock.get_display_size()
        self.clock_x = (self.width - clock_width) // 2
        clock_target_y = int((self.title_y + int(self.title_font_size * 1.5) + golden_upper) / 2)
        self.clock_y = max(clock_target_y - clock_height // 2, 
                          self.title_y + int(self.title_font_size * 1.8))
        
        # QR code at golden upper point with proportional sizing
        qr_base_size = min(self.width, self.height) * 0.16  # 16% of smaller dimension
        self.qr_size = int(qr_base_size)
        self.qr_x = (self.width - self.qr_size) // 2
        self.qr_y = int(golden_upper - self.qr_size // 2)
        
        # Ensure QR doesn't overlap with clock
        min_qr_y = self.clock_y + clock_height + int(self.qr_size * 0.1)
        if self.qr_y < min_qr_y:
            self.qr_y = min_qr_y
        
        # Subtitle below QR with proportional spacing
        subtitle = "Scan to access web interface"
        bbox = temp_draw.textbbox((0, 0), subtitle, font=self.subtitle_font)
        subtitle_width = bbox[2] - bbox[0]
        self.subtitle_x = (self.width - subtitle_width) // 2
        self.subtitle_y = self.qr_y + self.qr_size + int(self.qr_size * 0.15)  # 15% of QR size
        
        # Logo at golden lower point with proportional sizing
        logo_base_size = min(self.width, self.height) * 0.20  # Increased from 11% to 20%
        self.logo_size = max(int(logo_base_size), 120)  # Minimum 120px (doubled)
        self.logo_x = (self.width - self.logo_size) // 2
        self.logo_y = int(golden_lower - self.logo_size // 2)
        
        # Ensure logo has plenty of breathing room
        min_logo_y = self.subtitle_y + int(self.subtitle_font_size * 4)  # Much more space after subtitle text
        if self.logo_y < min_logo_y:
            self.logo_y = min_logo_y
        
        # Decorative elements with proportional spacing
        self.accent_width = int(self.width * 0.15)  # 15% of screen width
        self.accent_height = max(2, int(self.height * 0.004))  # 0.4% of screen height, minimum 2px
        self.accent_x = self.width // 2
        
        # Position lines with much more generous spacing from content
        # Upper line: halfway between title and clock with large margins
        title_bottom = self.title_y + self.title_font_size
        clock_top = self.clock_y
        available_upper_space = clock_top - title_bottom
        self.top_accent_y = title_bottom + int(available_upper_space * 0.5)  # Centered in the gap
        
        # Safety check for upper line - ensure clock doesn't overlap
        min_upper_clearance = int(self.title_font_size * 0.8)  # 80% of title font size below title
        max_upper_clearance = int(clock_height * 0.3)  # 30% of clock height above clock
        self.top_accent_y = max(title_bottom + min_upper_clearance,
                               min(self.top_accent_y, clock_top - max_upper_clearance))
        
        # Lower line: well spaced between subtitle text and logo
        subtitle_bottom = self.subtitle_y + self.subtitle_font_size
        logo_top = self.logo_y
        available_lower_space = logo_top - subtitle_bottom
        self.bottom_accent_y = subtitle_bottom + int(available_lower_space * 0.7)  # Closer to logo, further from text
        
        # Safety check for lower line - ensure generous clearance
        min_lower_clearance = int(self.subtitle_font_size * 2.0)  # 2x font size below subtitle text
        max_lower_clearance = int(self.logo_size * 0.2)  # 20% of logo size above logo
        self.bottom_accent_y = max(subtitle_bottom + min_lower_clearance,
                                  min(self.bottom_accent_y, logo_top - max_lower_clearance))
    
    def _create_qr_code(self) -> Image.Image:
        """Create QR code for server access"""
        if self._qr_image is None:
            hostname = os.uname().nodename
            server_url = f"http://{hostname}:8000"
            
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=max(5, int(8 * self.font_scale)),  # 35% bigger: 6 -> 8
                border=4,
            )
            qr.add_data(server_url)
            qr.make(fit=True)
            
            qr_img = qr.make_image(fill_color="white", back_color=self.bg_color)
            self._qr_image = qr_img.resize((self.qr_size, self.qr_size), Image.Resampling.NEAREST)
        
        return self._qr_image
    
    def _create_background_template(self) -> Image.Image:
        """Create static background template with title, QR, and decorative elements"""
        if self._background_template is not None:
            return self._background_template.copy()
        
        img = Image.new('RGB', (self.width, self.height), self.bg_color)
        draw = ImageDraw.Draw(img)
        
        # Draw title with glow effect
        title = "Hackerspace.gent Canvas"
        glow_offset = max(1, int(2 * self.font_scale))
        
        # Draw glow
        for offset in [(glow_offset, glow_offset), (-glow_offset, glow_offset), 
                      (glow_offset, -glow_offset), (-glow_offset, -glow_offset)]:
            draw.text((self.title_x + offset[0], self.title_y + offset[1]), 
                     title, fill=(50, 50, 50), font=self.title_font)
        
        # Draw title
        draw.text((self.title_x, self.title_y), title, fill=self.title_color, font=self.title_font)
        
        # Add QR code
        qr_img = self._create_qr_code()
        img.paste(qr_img, (self.qr_x, self.qr_y))
        
        # Draw subtitle with glow
        subtitle = "Scan to access web interface"
        glow_offset_small = glow_offset // 2
        
        for offset in [(glow_offset_small, glow_offset_small), (-glow_offset_small, glow_offset_small), 
                      (glow_offset_small, -glow_offset_small), (-glow_offset_small, -glow_offset_small)]:
            draw.text((self.subtitle_x + offset[0], self.subtitle_y + offset[1]), 
                     subtitle, fill=(50, 50, 50), font=self.subtitle_font)
        
        draw.text((self.subtitle_x, self.subtitle_y), subtitle, fill=self.subtitle_color, font=self.subtitle_font)
        
        # Draw decorative accent bars
        draw.rectangle([
            self.accent_x - self.accent_width, self.top_accent_y,
            self.accent_x + self.accent_width, self.top_accent_y + self.accent_height
        ], fill=self.accent_color)
        
        draw.rectangle([
            self.accent_x - self.accent_width, self.bottom_accent_y,
            self.accent_x + self.accent_width, self.bottom_accent_y + self.accent_height
        ], fill=self.accent_color)
        
        # Add logo image below the decorative line
        logo_path = "/home/hsg/srs_server/static/hsg_logo_invert.png"
        try:
            logo_image = Image.open(logo_path)
            logo_resized = logo_image.resize((self.logo_size, self.logo_size), Image.Resampling.LANCZOS)
            
            # Paste with transparency support
            if logo_resized.mode in ('RGBA', 'LA'):
                img.paste(logo_resized, (self.logo_x, self.logo_y), logo_resized)
            else:
                img.paste(logo_resized, (self.logo_x, self.logo_y))
                
        except Exception as e:
            import logging
            logging.warning(f"Could not load logo image for splitflap background: {e}")
        
        self._background_template = img
        return img.copy()
    
    def update(self) -> bool:
        """Update clock and return True if display needs refresh"""
        return self.clock.update()
    
    def render(self) -> Image.Image:
        """Render complete background with animated clock"""
        # Start with background template
        img = self._create_background_template()
        
        # Render and composite clock
        clock_img = self.clock.render(self.bg_color)
        img.paste(clock_img, (self.clock_x, self.clock_y))
        
        return img
    
    def get_current_time(self) -> str:
        """Get current displayed time"""
        return self.clock.get_current_time_string()
    
    def is_animating(self) -> bool:
        """Check if clock is currently animating"""
        return self.clock.is_any_animation_active()
    
    def force_time_update(self) -> None:
        """Force clock to update to current time"""
        self.clock.force_update()
        
    def clear_cache(self) -> None:
        """Clear cached background template (call if hostname changes)"""
        self._background_template = None
        self._qr_image = None