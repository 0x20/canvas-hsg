"""
Background Configuration System

Centralized configuration for all background generation parameters.
Provides easy customization of layout, spacing, sizes, and content.
"""

from typing import Tuple, Optional
from dataclasses import dataclass
import os


@dataclass
class BackgroundConfig:
    """
    Comprehensive configuration for background generation.
    
    All spacing values are as percentages of canvas height (0.0 to 1.0)
    All size percentages are relative to canvas dimensions
    """
    
    # Canvas settings
    background_color: Tuple[int, int, int] = (20, 20, 30)
    canvas_padding: float = 0.05  # 5% padding around edges
    
    # Global spacing settings (as percentages of canvas height)
    default_component_spacing: float = 0.025  # 2.5% default spacing between components
    
    # Component-specific spacing (overrides default if set)
    title_spacing_after: float = 0.015  # 1.5% space after title
    upper_line_spacing_before: float = 0.0   # No lines
    upper_line_spacing_after: float = 0.0    # No lines
    qr_spacing_before: float = 0.015    # 1.5% space before QR code
    qr_spacing_after: float = 0.015     # 1.5% space after QR code
    text_spacing_after: float = 0.015   # 1.5% space after subtitle text
    lower_line_spacing_before: float = 0.0   # No lines
    lower_line_spacing_after: float = 0.0    # No lines
    logo_spacing_before: float = 0.015  # 1.5% space before logo
    clock_spacing_before: float = 0.01  # 1% space before clock
    clock_spacing_after: float = 0.015  # 1.5% space after clock
    
    # Title settings
    title_text: str = "Hackerspace.gent Canvas"
    title_font_scale: float = 1.0
    title_color: Tuple[int, int, int] = (100, 150, 255)
    title_glow_enabled: bool = True
    title_glow_color: Tuple[int, int, int] = (50, 50, 50)
    title_glow_offset: float = 0.025  # As percentage of font size
    
    # Line settings (disabled - lines removed)
    line_width_percent: float = 0.0     # 0% - lines disabled
    upper_line_height_px: int = 0       # Disabled
    lower_line_height_px: int = 0       # Disabled  
    line_height_px: int = 0             # Disabled
    line_color: Tuple[int, int, int] = (100, 150, 255)
    
    # QR Code settings  
    qr_size_percent: float = 0.12       # 12% of canvas height
    qr_box_size_scale: float = 1.0      # Multiplier for QR box size
    qr_border: int = 4                  # QR code border size
    qr_foreground_color: str = "white"
    qr_background_color: Optional[Tuple[int, int, int]] = None  # None = use canvas background
    
    # Subtitle text settings
    subtitle_text: str = "Scan to access web interface"
    subtitle_font_scale: float = 1.5    # Larger text but reasonable
    subtitle_color: Tuple[int, int, int] = (180, 180, 180)
    subtitle_glow_enabled: bool = True
    subtitle_glow_color: Tuple[int, int, int] = (50, 50, 50)
    subtitle_glow_offset: float = 0.5   # As percentage of font size
    
    # Logo settings
    logo_path: str = "/home/hsg/srs_server/static/hsg_logo_invert.png"
    logo_size_percent: float = 0.12     # 12% of canvas height
    logo_min_size: int = 100            # Minimum logo size in pixels
    logo_max_size: int = 300            # Maximum logo size in pixels
    
    # Clock settings (for splitflap mode)
    clock_digit_width_scale: float = 1.4   # Multiplier for clock digit width (increased from 1.0)
    clock_digit_height_scale: float = 1.4  # Multiplier for clock digit height (increased from 1.0)
    clock_font_scale: float = 1.4          # Multiplier for clock font size (increased from 1.0)
    clock_spacing_scale: float = 1.2       # Multiplier for clock digit spacing (slightly increased)
    
    # Font settings
    title_font_path: str = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    subtitle_font_path: str = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    fallback_to_default_font: bool = True
    
    # Layout algorithm settings
    layout_algorithm: str = "vertical_flow"  # "vertical_flow", "golden_ratio", "rule_of_thirds"
    center_horizontally: bool = True
    vertical_alignment: str = "distribute"   # "top", "center", "bottom", "distribute"
    
    # Resolution scaling
    base_resolution_width: int = 1920   # Reference resolution for scaling
    base_resolution_height: int = 1080
    scale_with_resolution: bool = True
    
    def get_server_url(self) -> str:
        """Get the server URL for QR code generation"""
        hostname = os.uname().nodename
        return f"http://{hostname}:8000"
    
    def get_qr_background_color(self) -> Tuple[int, int, int]:
        """Get QR background color, defaulting to canvas background if not set"""
        return self.qr_background_color or self.background_color
    
    def calculate_font_scale(self, canvas_width: int, canvas_height: int) -> float:
        """Calculate font scaling factor based on canvas resolution"""
        if not self.scale_with_resolution:
            return 1.0
            
        width_scale = canvas_width / self.base_resolution_width
        height_scale = canvas_height / self.base_resolution_height
        return min(width_scale, height_scale)
    
    def get_title_font_size(self, canvas_width: int, canvas_height: int) -> int:
        """Get scaled title font size - 8% of canvas height"""
        # Title should be 8% of canvas height
        target_size = int(canvas_height * 0.08)
        return int(target_size * self.title_font_scale)
    
    def get_subtitle_font_size(self, canvas_width: int, canvas_height: int) -> int:
        """Get scaled subtitle font size - 4% of canvas height"""
        # Subtitle should be 4% of canvas height
        target_size = int(canvas_height * 0.04)
        return int(target_size * self.subtitle_font_scale)
    
    def to_dict(self) -> dict:
        """Convert config to dictionary for serialization"""
        return {
            field.name: getattr(self, field.name)
            for field in self.__dataclass_fields__.values()
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'BackgroundConfig':
        """Create config from dictionary"""
        # Filter data to only include valid fields
        valid_fields = {field.name for field in cls.__dataclass_fields__.values()}
        filtered_data = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**filtered_data)
    
    def copy(self) -> 'BackgroundConfig':
        """Create a copy of this configuration"""
        return BackgroundConfig(**self.to_dict())
    
    def validate(self) -> list:
        """Validate configuration and return list of issues"""
        issues = []
        
        # Check percentage values are in valid range
        percentage_fields = [
            'canvas_padding', 'default_component_spacing', 'title_spacing_after',
            'qr_spacing_before', 'qr_spacing_after', 'text_spacing_after',
            'logo_spacing_before', 'line_width_percent', 'qr_size_percent',
            'logo_size_percent'
        ]
        
        for field in percentage_fields:
            value = getattr(self, field)
            if not 0 <= value <= 1:
                issues.append(f"{field} must be between 0 and 1, got {value}")
        
        # Check file paths exist
        if not os.path.exists(self.logo_path):
            issues.append(f"Logo file not found: {self.logo_path}")
        
        if not os.path.exists(self.title_font_path):
            if not self.fallback_to_default_font:
                issues.append(f"Title font not found: {self.title_font_path}")
        
        if not os.path.exists(self.subtitle_font_path):
            if not self.fallback_to_default_font:
                issues.append(f"Subtitle font not found: {self.subtitle_font_path}")
        
        # Check color values
        color_fields = ['background_color', 'title_color', 'line_color', 'subtitle_color']
        for field in color_fields:
            color = getattr(self, field)
            if not (isinstance(color, tuple) and len(color) == 3 and 
                   all(0 <= c <= 255 for c in color)):
                issues.append(f"{field} must be RGB tuple (0-255), got {color}")
        
        return issues


# Predefined configuration presets
class ConfigPresets:
    """Predefined configuration presets for different use cases"""
    
    @staticmethod
    def default() -> BackgroundConfig:
        """Default configuration"""
        return BackgroundConfig()
    
    @staticmethod
    def compact() -> BackgroundConfig:
        """Compact layout with smaller spacing"""
        config = BackgroundConfig()
        config.default_component_spacing = 0.015
        config.title_spacing_after = 0.025
        config.qr_spacing_before = 0.02
        config.qr_spacing_after = 0.01
        config.text_spacing_after = 0.02
        config.logo_spacing_before = 0.025
        config.canvas_padding = 0.03
        return config
    
    @staticmethod
    def spacious() -> BackgroundConfig:
        """Spacious layout with larger spacing"""
        config = BackgroundConfig()
        config.default_component_spacing = 0.04
        config.title_spacing_after = 0.06
        config.qr_spacing_before = 0.04
        config.qr_spacing_after = 0.03
        config.text_spacing_after = 0.05
        config.logo_spacing_before = 0.06
        config.canvas_padding = 0.08
        return config
    
    @staticmethod
    def large_logo() -> BackgroundConfig:
        """Configuration with larger logo and QR code"""
        config = BackgroundConfig()
        config.qr_size_percent = 0.22
        config.logo_size_percent = 0.25
        config.logo_min_size = 150
        return config
    
    @staticmethod
    def minimal() -> BackgroundConfig:
        """Minimal design with no decorative lines"""
        config = BackgroundConfig()
        config.line_width_percent = 0.0  # Hide lines by setting width to 0
        config.title_glow_enabled = False
        config.subtitle_glow_enabled = False
        return config