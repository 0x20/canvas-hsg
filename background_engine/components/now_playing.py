"""
Now Playing Component

Renders album art alongside track name, artist, and album text
for Spotify "Now Playing" display on the physical screen.
"""

from typing import Tuple, Optional
from PIL import Image, ImageFont, ImageDraw
import logging

from ..layout import LayoutComponent
from ..config import BackgroundConfig


class NowPlayingComponent(LayoutComponent):
    """Component for rendering now-playing info: album art + track/artist/album text"""

    def __init__(self, track_name: str = "", artists: str = "", album: str = "",
                 album_art_path: Optional[str] = None, component_id: str = "now_playing"):
        super().__init__(component_id)
        self.track_name = track_name
        self.artists = artists
        self.album = album
        self.album_art_path = album_art_path
        self._font_cache = {}
        self._album_art_cache: Optional[Image.Image] = None

    def _load_font(self, size: int, config: BackgroundConfig, bold: bool = False) -> ImageFont.ImageFont:
        """Load font with caching"""
        font_path = config.title_font_path if bold else config.subtitle_font_path
        cache_key = (font_path, size)

        if cache_key not in self._font_cache:
            try:
                font = ImageFont.truetype(font_path, size)
                self._font_cache[cache_key] = font
            except Exception as e:
                if config.fallback_to_default_font:
                    logging.warning(f"Could not load font {font_path}: {e}, using default")
                    font = ImageFont.load_default()
                    self._font_cache[cache_key] = font
                else:
                    raise e

        return self._font_cache[cache_key]

    def _load_album_art(self, target_size: int) -> Optional[Image.Image]:
        """Load and resize album art image"""
        if not self.album_art_path:
            return None

        if self._album_art_cache is not None:
            return self._album_art_cache

        try:
            img = Image.open(self.album_art_path)
            if img.mode != 'RGB':
                img = img.convert('RGB')
            img = img.resize((target_size, target_size), Image.Resampling.LANCZOS)
            self._album_art_cache = img
            return img
        except Exception as e:
            logging.warning(f"Could not load album art {self.album_art_path}: {e}")
            return None

    def calculate_size(self, canvas_width: int, canvas_height: int,
                      config: BackgroundConfig) -> Tuple[int, int]:
        """Calculate component size: art square + text block side by side"""
        art_size = int(canvas_height * 0.35)
        # Width spans most of the canvas
        total_width = int(canvas_width * 0.8)
        return total_width, art_size

    def render(self, draw: ImageDraw.Draw, x: int, y: int, width: int, height: int,
               canvas_width: int, canvas_height: int, config: BackgroundConfig) -> None:
        """Render album art and track info text"""
        art_size = height
        art_padding = int(art_size * 0.08)  # gap between art and text

        # Font sizes relative to the art square height
        track_font_size = int(art_size * 0.18)
        artist_font_size = int(art_size * 0.14)
        album_font_size = int(art_size * 0.11)

        track_font = self._load_font(track_font_size, config, bold=True)
        artist_font = self._load_font(artist_font_size, config, bold=False)
        album_font = self._load_font(album_font_size, config, bold=False)

        # Load album art
        album_art = self._load_album_art(art_size)

        if album_art:
            # Paste album art onto the underlying image
            # We need access to the actual Image, not just ImageDraw
            # ImageDraw's _image gives us the underlying PIL Image
            try:
                img = draw._image
                img.paste(album_art, (x, y))
            except Exception as e:
                logging.warning(f"Could not paste album art: {e}")
                # Draw a placeholder square
                draw.rectangle([x, y, x + art_size, y + art_size], fill=(40, 40, 60))

            text_x = x + art_size + art_padding
        else:
            # No album art - draw a placeholder and still offset text
            draw.rectangle([x, y, x + art_size, y + art_size], fill=(40, 40, 60))
            # Draw a music note symbol in the placeholder
            note_font = self._load_font(int(art_size * 0.4), config, bold=True)
            note_bbox = note_font.getbbox("\u266b")
            note_w = note_bbox[2] - note_bbox[0]
            note_h = note_bbox[3] - note_bbox[1]
            draw.text(
                (x + (art_size - note_w) // 2, y + (art_size - note_h) // 2),
                "\u266b", fill=(80, 80, 120), font=note_font
            )
            text_x = x + art_size + art_padding

        # Available width for text
        text_max_width = width - art_size - art_padding

        # Vertically center the text block within the art height
        # Calculate total text height first
        line_spacing = int(art_size * 0.06)

        track_bbox = track_font.getbbox(self.track_name or "Unknown Track")
        artist_bbox = artist_font.getbbox(self.artists or "Unknown Artist")
        album_bbox = album_font.getbbox(self.album or "")

        track_h = track_bbox[3] - track_bbox[1]
        artist_h = artist_bbox[3] - artist_bbox[1]
        album_h = album_bbox[3] - album_bbox[1] if self.album else 0

        total_text_h = track_h + line_spacing + artist_h
        if self.album:
            total_text_h += line_spacing + album_h

        text_y = y + (art_size - total_text_h) // 2

        # Track name (large, bright)
        track_text = self._truncate_text(self.track_name or "Unknown Track", track_font, text_max_width)
        draw.text((text_x, text_y), track_text, fill=(255, 255, 255), font=track_font)
        text_y += track_h + line_spacing

        # Artists (medium, slightly dimmer)
        artist_text = self._truncate_text(self.artists or "Unknown Artist", artist_font, text_max_width)
        draw.text((text_x, text_y), artist_text, fill=(180, 200, 255), font=artist_font)
        text_y += artist_h + line_spacing

        # Album (small, dimmer)
        if self.album:
            album_text = self._truncate_text(self.album, album_font, text_max_width)
            draw.text((text_x, text_y), album_text, fill=(140, 140, 170), font=album_font)

    def _truncate_text(self, text: str, font: ImageFont.ImageFont, max_width: int) -> str:
        """Truncate text with ellipsis if it exceeds max_width"""
        bbox = font.getbbox(text)
        if (bbox[2] - bbox[0]) <= max_width:
            return text

        # Binary search for the right truncation point
        ellipsis = "..."
        lo, hi = 0, len(text)
        while lo < hi:
            mid = (lo + hi + 1) // 2
            test = text[:mid] + ellipsis
            bbox = font.getbbox(test)
            if (bbox[2] - bbox[0]) <= max_width:
                lo = mid
            else:
                hi = mid - 1

        return text[:lo] + ellipsis if lo > 0 else ellipsis

    def get_min_size(self, canvas_width: int, canvas_height: int,
                    config: BackgroundConfig) -> Tuple[int, int]:
        """Minimum size for readable now-playing display"""
        min_art = 100
        return min_art * 3, min_art
