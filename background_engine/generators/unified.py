"""
Unified Background Generator

High-level generator that combines layout engine and components to create
complete backgrounds for both static and splitflap modes.
"""

from typing import Optional, TYPE_CHECKING
from pathlib import Path
from PIL import Image
import logging

from ..config import BackgroundConfig, ConfigPresets
from ..layout import LayoutEngine
from ..components import TitleComponent, LineComponent, QRCodeComponent, TextComponent, LogoComponent, ClockComponent, AudioIconComponent, NowPlayingComponent

if TYPE_CHECKING:
    from ...splitflap.clock import SplitflapClock


class UnifiedBackgroundGenerator:
    """
    Unified generator for creating both static and splitflap backgrounds
    using the modular component and layout system.
    """
    
    def __init__(self, config: Optional[BackgroundConfig] = None):
        """
        Initialize the background generator.
        
        Args:
            config: Background configuration. If None, uses default config.
        """
        self.config = config or BackgroundConfig()
        
        # Validate configuration
        issues = self.config.validate()
        if issues:
            logging.warning(f"Background configuration issues: {issues}")
    
    def create_static_background(self, width: int, height: int, 
                                config_override: Optional[BackgroundConfig] = None,
                                title_height_percent: float = 0.10,    # Larger title (increased from 0.08)
                                title_spacing_percent: float = 0.05,   # More space after title (increased from 0.02)
                                qr_height_percent: float = 0.20,       # Larger QR code (increased from 0.12)
                                qr_spacing_percent: float = 0.04,      # More space around QR (increased from 0.02)
                                text_height_percent: float = 0.06,     # Larger text (increased from 0.04)
                                text_spacing_percent: float = 0.04,    # More space around text (increased from 0.02)
                                logo_height_percent: float = 0.18,     # Larger logo (increased from 0.12)
                                logo_spacing_percent: float = 0.03,    # Space after logo
                                show_audio_icon: bool = False) -> Image.Image:
        """
        Create a static background with title, lines, QR code, text, and logo.
        
        Args:
            width: Canvas width in pixels
            height: Canvas height in pixels
            config_override: Optional config override for this generation
            
        Returns:
            PIL Image with rendered background
        """
        config = config_override or self.config
        
        # Create layout engine
        engine = LayoutEngine(width, height, config)
        
        # Add components with direct height control
        # Calculate absolute heights from percentages
        title_height = int(height * title_height_percent)
        qr_height = int(height * qr_height_percent)
        text_height = int(height * text_height_percent)
        logo_height = int(height * logo_height_percent)
        
        title_spacing = int(height * title_spacing_percent)
        qr_spacing = int(height * qr_spacing_percent)
        text_spacing = int(height * text_spacing_percent)
        logo_spacing = int(height * logo_spacing_percent)
        
        # Force component sizes by overriding their calculate_size methods
        title_comp = TitleComponent(component_id="main_title")
        title_comp.calculate_size = lambda cw, ch, cfg: (width, title_height)
        
        qr_comp = QRCodeComponent(component_id="qr_code")
        qr_comp.calculate_size = lambda cw, ch, cfg: (qr_height, qr_height)
        
        text_comp = TextComponent(config.subtitle_text, component_id="subtitle")
        text_comp.calculate_size = lambda cw, ch, cfg: (width, text_height)
        
        logo_comp = LogoComponent(component_id="logo")
        logo_comp.calculate_size = lambda cw, ch, cfg: (logo_height, logo_height)
        
        engine.add_component(title_comp, spacing_after=title_spacing)
        engine.add_component(qr_comp, spacing_after=qr_spacing)
        engine.add_component(text_comp, spacing_after=text_spacing)
        engine.add_component(logo_comp, spacing_after=logo_spacing)
        
        # Add audio icon if audio is playing
        if show_audio_icon:
            audio_icon_comp = AudioIconComponent(component_id="audio_icon")
            # Small icon, positioned after logo
            audio_icon_height = int(height * 0.08)  # 8% of screen height
            audio_icon_comp.calculate_size = lambda cw, ch, cfg: (audio_icon_height, audio_icon_height)
            engine.add_component(audio_icon_comp, spacing_after=int(height * 0.02))
        
        # Render and return
        try:
            return engine.render()
        except Exception as e:
            logging.error(f"Failed to render static background: {e}")
            # Return a simple fallback background
            return self._create_fallback_background(width, height, config)
    
    def create_now_playing_background(self, width: int, height: int,
                                      track_name: str, artists: str,
                                      album: str = "",
                                      album_art_path: str = None,
                                      config_override: 'Optional[BackgroundConfig]' = None) -> Image.Image:
        """
        Create a "Now Playing" background with fullscreen album art and large track/artist text overlay.

        Args:
            width: Canvas width in pixels
            height: Canvas height in pixels
            track_name: Song title
            artists: Comma-separated artist names
            album: Album name
            album_art_path: Path to downloaded album art image
            config_override: Optional config override

        Returns:
            PIL Image with rendered now-playing background
        """
        config = config_override or self.config

        from PIL import ImageDraw, ImageFont, ImageFilter

        # Load and scale album art to fill entire screen
        if album_art_path and Path(album_art_path).exists():
            try:
                art = Image.open(album_art_path)
                if art.mode != 'RGB':
                    art = art.convert('RGB')

                # Scale to fill screen (cover mode)
                img_aspect = art.width / art.height
                screen_aspect = width / height

                if img_aspect > screen_aspect:
                    # Image is wider - fit to height
                    new_height = height
                    new_width = int(art.width * (height / art.height))
                else:
                    # Image is taller - fit to width
                    new_width = width
                    new_height = int(art.height * (width / art.width))

                art = art.resize((new_width, new_height), Image.Resampling.LANCZOS)

                # Crop to center if needed
                left = (new_width - width) // 2
                top = (new_height - height) // 2
                art = art.crop((left, top, left + width, top + height))

                # Apply slight blur and darken for text readability
                img = art.filter(ImageFilter.GaussianBlur(radius=3))
                img = img.point(lambda p: int(p * 0.7))  # Darken to 70%

            except Exception as e:
                logging.warning(f"Failed to load album art: {e}")
                # Fallback to dark gradient
                img = Image.new('RGB', (width, height), (15, 15, 25))
        else:
            # No album art - use dark gradient background
            img = Image.new('RGB', (width, height), (15, 15, 25))

        draw = ImageDraw.Draw(img)

        # Load fonts - using DejaVu Sans (clean, modern sans-serif)
        font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
        try:
            track_font = ImageFont.truetype(font_path, int(height * 0.12))  # 12% of screen height
            artist_font = ImageFont.truetype(font_path, int(height * 0.075))  # 7.5% of screen height
        except:
            # Fallback to default font
            track_font = ImageFont.load_default()
            artist_font = ImageFont.load_default()

        # Text positioning - top left
        text_y_start = 50  # Top of screen
        padding = 80
        max_text_width = width - (2 * padding)

        # Draw track name with shadow for readability
        track_bbox = track_font.getbbox(track_name)
        track_h = track_bbox[3] - track_bbox[1]

        # Shadow
        draw.text((padding + 4, text_y_start + 4), track_name, fill=(0, 0, 0), font=track_font)
        # Main text
        draw.text((padding, text_y_start), track_name, fill=(255, 255, 255), font=track_font)

        # Draw artist below track
        artist_y = text_y_start + track_h + 30

        # Shadow
        draw.text((padding + 3, artist_y + 3), artists, fill=(0, 0, 0), font=artist_font)
        # Main text
        draw.text((padding, artist_y), artists, fill=(200, 220, 255), font=artist_font)

        return img

    def create_splitflap_background(self, width: int, height: int,
                                   splitflap_clock: 'SplitflapClock',
                                   config_override: Optional[BackgroundConfig] = None,
                                   title_height_percent: float = 0.08,    # Slightly smaller title for splitflap mode
                                   title_spacing_percent: float = 0.03,   # Space after title
                                   clock_height_percent: float = 0.15,    # Clock size
                                   clock_spacing_percent: float = 0.03,   # Space around clock
                                   qr_height_percent: float = 0.18,       # Larger QR code (increased from 0.12)
                                   qr_spacing_percent: float = 0.03,      # Space around QR
                                   text_height_percent: float = 0.05,     # Larger text (increased from 0.04)
                                   text_spacing_percent: float = 0.03,    # Space around text
                                   logo_height_percent: float = 0.16,     # Larger logo (increased from 0.12)
                                   logo_spacing_percent: float = 0.02) -> Image.Image:    # Space after logo
        """
        Create a splitflap background with title, lines, clock, QR code, text, and logo.
        
        Args:
            width: Canvas width in pixels
            height: Canvas height in pixels
            splitflap_clock: The splitflap clock instance to render
            config_override: Optional config override for this generation
            
        Returns:
            PIL Image with rendered background including splitflap clock
        """
        config = config_override or self.config
        
        # Create layout engine
        engine = LayoutEngine(width, height, config)
        
        # Add components with direct height control
        # Calculate absolute heights from percentages
        title_height = int(height * title_height_percent)
        clock_height = int(height * clock_height_percent)
        qr_height = int(height * qr_height_percent)
        text_height = int(height * text_height_percent)
        logo_height = int(height * logo_height_percent)
        
        title_spacing = int(height * title_spacing_percent)
        clock_spacing = int(height * clock_spacing_percent)
        qr_spacing = int(height * qr_spacing_percent)
        text_spacing = int(height * text_spacing_percent)
        logo_spacing = int(height * logo_spacing_percent)
        
        # Force component sizes by overriding their calculate_size methods
        title_comp = TitleComponent(component_id="main_title")
        title_comp.calculate_size = lambda cw, ch, cfg: (width, title_height)
        
        clock_comp = ClockComponent(splitflap_clock, component_id="splitflap_clock")
        clock_comp.calculate_size = lambda cw, ch, cfg: (splitflap_clock.total_width, clock_height)
        
        qr_comp = QRCodeComponent(component_id="qr_code")
        qr_comp.calculate_size = lambda cw, ch, cfg: (qr_height, qr_height)
        
        text_comp = TextComponent(config.subtitle_text, component_id="subtitle")
        text_comp.calculate_size = lambda cw, ch, cfg: (width, text_height)
        
        logo_comp = LogoComponent(component_id="logo")
        logo_comp.calculate_size = lambda cw, ch, cfg: (logo_height, logo_height)
        
        engine.add_component(title_comp, spacing_after=title_spacing)
        engine.add_component(clock_comp, spacing_after=clock_spacing)
        engine.add_component(qr_comp, spacing_after=qr_spacing)
        engine.add_component(text_comp, spacing_after=text_spacing)
        engine.add_component(logo_comp, spacing_after=logo_spacing)
        
        # Render and return
        try:
            return engine.render()
        except Exception as e:
            logging.error(f"Failed to render splitflap background: {e}")
            # Return a simple fallback background
            return self._create_fallback_background(width, height, config)
    
    def _create_fallback_background(self, width: int, height: int, 
                                   config: BackgroundConfig) -> Image.Image:
        """Create a simple fallback background when rendering fails"""
        img = Image.new('RGB', (width, height), config.background_color)
        
        try:
            from PIL import ImageDraw, ImageFont
            draw = ImageDraw.Draw(img)
            
            # Try to draw simple text
            font = ImageFont.load_default()
            text = "HSG Canvas"
            text_bbox = font.getbbox(text)
            text_width = text_bbox[2] - text_bbox[0]
            text_height = text_bbox[3] - text_bbox[1]
            
            text_x = (width - text_width) // 2
            text_y = (height - text_height) // 2
            
            draw.text((text_x, text_y), text, fill=(255, 255, 255), font=font)
            
        except Exception:
            pass  # If even fallback fails, just return solid color
        
        return img
    
    def get_layout_info(self, width: int, height: int, mode: str = "static",
                       splitflap_clock: Optional['SplitflapClock'] = None) -> dict:
        """
        Get detailed layout information for debugging and configuration.
        
        Args:
            width: Canvas width
            height: Canvas height
            mode: "static" or "splitflap"
            splitflap_clock: Clock instance for splitflap mode
            
        Returns:
            Dictionary with layout information
        """
        engine = LayoutEngine(width, height, self.config)
        
        # Add components based on mode
        if mode == "static":
            engine.add_component(TitleComponent(component_id="main_title"))
            engine.add_component(LineComponent(component_id="upper_line"))
            engine.add_component(QRCodeComponent(component_id="qr_code"))
            engine.add_component(TextComponent(self.config.subtitle_text, component_id="subtitle"))
            engine.add_component(LineComponent(component_id="lower_line"))
            engine.add_component(LogoComponent(component_id="logo"))
        else:  # splitflap
            if not splitflap_clock:
                raise ValueError("splitflap_clock required for splitflap mode layout info")
            
            engine.add_component(TitleComponent(component_id="main_title"))
            engine.add_component(LineComponent(component_id="upper_line"))
            engine.add_component(ClockComponent(splitflap_clock, component_id="splitflap_clock"))
            engine.add_component(QRCodeComponent(component_id="qr_code"))
            engine.add_component(TextComponent(self.config.subtitle_text, component_id="subtitle"))
            engine.add_component(LineComponent(component_id="lower_line"))
            engine.add_component(LogoComponent(component_id="logo"))
        
        layout_info = engine.get_layout_info()
        layout_info['mode'] = mode
        layout_info['config'] = self.config.to_dict()
        
        return layout_info
    
    def create_preview_grid(self, width: int, height: int, 
                           splitflap_clock: Optional['SplitflapClock'] = None) -> Image.Image:
        """
        Create a preview grid showing different configuration presets.
        
        Args:
            width: Canvas width for each preview
            height: Canvas height for each preview
            splitflap_clock: Clock instance for splitflap previews
            
        Returns:
            PIL Image with 2x2 grid of different background styles
        """
        try:
            # Create previews with different presets
            preview_width = width // 2
            preview_height = height // 2
            
            previews = [
                ("Default", self.create_static_background(preview_width, preview_height)),
                ("Compact", self.create_static_background(preview_width, preview_height, ConfigPresets.compact())),
                ("Spacious", self.create_static_background(preview_width, preview_height, ConfigPresets.spacious())),
                ("Large Logo", self.create_static_background(preview_width, preview_height, ConfigPresets.large_logo()))
            ]
            
            # Create grid
            grid = Image.new('RGB', (width, height), (40, 40, 40))
            
            for i, (name, preview) in enumerate(previews):
                x = (i % 2) * preview_width
                y = (i // 2) * preview_height
                grid.paste(preview, (x, y))
                
                # Add label
                try:
                    from PIL import ImageDraw, ImageFont
                    draw = ImageDraw.Draw(grid)
                    font = ImageFont.load_default()
                    draw.text((x + 10, y + 10), name, fill=(255, 255, 255), font=font)
                except:
                    pass
            
            return grid
            
        except Exception as e:
            logging.error(f"Failed to create preview grid: {e}")
            return self._create_fallback_background(width, height, self.config)
    
    def update_config(self, **kwargs) -> None:
        """
        Update configuration with new values.
        
        Args:
            **kwargs: Configuration parameters to update
        """
        config_dict = self.config.to_dict()
        config_dict.update(kwargs)
        self.config = BackgroundConfig.from_dict(config_dict)
        
        # Validate updated configuration
        issues = self.config.validate()
        if issues:
            logging.warning(f"Updated background configuration issues: {issues}")
    
    def reset_config(self, preset: str = "default") -> None:
        """
        Reset configuration to a preset.
        
        Args:
            preset: Preset name ("default", "compact", "spacious", "large_logo", "minimal")
        """
        if preset == "default":
            self.config = ConfigPresets.default()
        elif preset == "compact":
            self.config = ConfigPresets.compact()
        elif preset == "spacious":
            self.config = ConfigPresets.spacious()
        elif preset == "large_logo":
            self.config = ConfigPresets.large_logo()
        elif preset == "minimal":
            self.config = ConfigPresets.minimal()
        else:
            logging.warning(f"Unknown preset '{preset}', using default")
            self.config = ConfigPresets.default()