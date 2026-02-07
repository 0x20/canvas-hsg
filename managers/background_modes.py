"""
Background Mode Management for HSG Canvas
Handles static background image display with scaling and centering.
"""

import asyncio
import os
import time
import logging
from pathlib import Path
from typing import Optional, Any
from PIL import Image

from config import DEFAULT_BACKGROUND_PATH


class BackgroundManager:
    """Manages static background image display"""

    def __init__(self, display_detector, framebuffer_manager, video_pool=None):
        self.display_detector = display_detector
        self.framebuffer = framebuffer_manager
        self.video_pool = video_pool

        # Current state
        self.is_running = False
        
        # Static background image path - set to canvas_background.png by default
        self.static_background_image = DEFAULT_BACKGROUND_PATH
        
        # Verify the default background exists
        if not os.path.exists(self.static_background_image):
            logging.warning(f"Default background image not found: {self.static_background_image}")
            self.static_background_image = None
        
        # Paths
        self.temp_dir = Path("/tmp/stream_images")
        self.temp_dir.mkdir(exist_ok=True)
        self.current_background_path = self.temp_dir / "current_background.png"
    
    async def start_static_mode(self, force_redisplay: bool = False) -> bool:
        """Start static background display

        Args:
            force_redisplay: If True, redisplay even if already running
        """
        try:
            if self.is_running and not force_redisplay:
                return True

            logging.info("Starting static background mode")
            await self._start_static_mode()
            self.is_running = True
            return True

        except Exception as e:
            logging.error(f"Failed to start static background mode: {e}")
            return False
    
    async def start_static_mode_with_audio_status(self, show_audio_icon: bool = False) -> bool:
        """Start static background mode with audio status icon"""
        try:
            await self.stop()
            
            logging.info(f"Starting static background mode (audio icon: {show_audio_icon})")
            await self._start_static_mode(show_audio_icon=show_audio_icon)
            self.is_running = True
            return True
            
        except Exception as e:
            logging.error(f"Failed to start static background mode: {e}")
            return False
    
    async def _start_static_mode(self, show_audio_icon: bool = False) -> None:
        """Start static background mode"""
        await self._create_static_background(show_audio_icon=show_audio_icon)
        await self._display_current_background()
    
    async def _create_static_background(self, show_audio_icon: bool = False) -> None:
        """Scale and display static background image to monitor resolution"""
        try:
            # Get optimal resolution
            display_config = self.display_detector.get_optimal_framebuffer_config()
            width, height = display_config['width'], display_config['height']
            
            if not self.static_background_image or not os.path.exists(self.static_background_image):
                # Create a simple fallback background if no image is set
                img = Image.new('RGB', (width, height), (20, 20, 30))
                logging.warning(f"No background image set, using fallback color: {width}x{height}")
            else:
                # Load and scale the static background image
                img = self._scale_image_to_resolution(self.static_background_image, width, height)
                logging.info(f"Scaled background image to: {width}x{height}")
            
            # Save scaled background with fast compression for quicker loading
            # compress_level=1 (fastest) instead of default 6 - trades file size for speed
            img.save(str(self.current_background_path), compress_level=1)
            
        except Exception as e:
            logging.error(f"Failed to create static background: {e}")
            # Create fallback background
            display_config = self.display_detector.get_optimal_framebuffer_config()
            width, height = display_config['width'], display_config['height']
            img = Image.new('RGB', (width, height), (20, 20, 30))
            img.save(str(self.current_background_path))
    
    async def _display_current_background(self) -> None:
        """Display the current background image using video pool mpv (seamless!)"""
        if not self.current_background_path.exists():
            raise RuntimeError("No background image to display")

        # Use video pool to display background - seamless content switching!
        if not self.video_pool or not self.video_pool.processes:
            raise RuntimeError("Video pool not available for background display")

        # Get idle controller from video pool
        controller = await self.video_pool.get_available_controller()
        if not controller:
            raise RuntimeError("No available video pool controller for background")

        # Set loop-file to infinite (mpv already started with --fs so fullscreen is automatic)
        await controller.send_command(["set", "loop-file", "inf"])

        # Load background image - will display fullscreen instantly
        # Note: mpv is started with --no-ytdl to prevent yt-dlp from probing the image file
        await controller.send_command(["loadfile", str(self.current_background_path)])

        # Release controller back to pool (it keeps playing the background)
        await self.video_pool.release_controller(controller)

        logging.info("Background displayed using video pool (seamless content switching)")

    def set_background_image(self, image_path: str) -> bool:
        """Set the static background image path"""
        try:
            if not os.path.exists(image_path):
                logging.error(f"Background image not found: {image_path}")
                return False
            
            # Verify it's a valid image
            with Image.open(image_path) as img:
                img.verify()
            
            self.static_background_image = image_path
            logging.info(f"Set background image: {image_path}")
            return True
            
        except Exception as e:
            logging.error(f"Invalid background image {image_path}: {e}")
            return False
    
    def _scale_image_to_resolution(self, image_path: str, target_width: int, target_height: int) -> Image.Image:
        """Scale image to target resolution while preserving aspect ratio"""
        try:
            with Image.open(image_path) as img:
                # Convert to RGB if necessary
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                
                # Get original dimensions
                orig_width, orig_height = img.size
                
                logging.info(f"Original image: {orig_width}x{orig_height}, Target: {target_width}x{target_height}")
                
                # If image already matches target resolution exactly, return as-is
                if orig_width == target_width and orig_height == target_height:
                    logging.info("Image already matches target resolution - no scaling needed")
                    return img.copy()
                
                # Calculate scaling factor to fit within target dimensions
                width_ratio = target_width / orig_width
                height_ratio = target_height / orig_height
                scale_factor = min(width_ratio, height_ratio)
                
                # Calculate new dimensions
                new_width = int(orig_width * scale_factor)
                new_height = int(orig_height * scale_factor)
                
                logging.info(f"Scale factor: {scale_factor:.3f}, New size: {new_width}x{new_height}")
                
                # If scale factor is 1 and dimensions match, no need for canvas
                if scale_factor == 1.0 and new_width == target_width and new_height == target_height:
                    logging.info("Perfect 1:1 scale - returning original")
                    return img.copy()
                
                # Resize image
                scaled_img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                
                # Create target canvas and center the scaled image
                canvas = Image.new('RGB', (target_width, target_height), (0, 0, 0))
                x_offset = (target_width - new_width) // 2
                y_offset = (target_height - new_height) // 2
                canvas.paste(scaled_img, (x_offset, y_offset))
                
                logging.info(f"Scaled and centered: offset ({x_offset}, {y_offset})")
                return canvas
                
        except Exception as e:
            logging.error(f"Failed to scale image {image_path}: {e}")
            # Return black canvas as fallback
            return Image.new('RGB', (target_width, target_height), (0, 0, 0))
    
    async def start_now_playing_mode(self, track_name: str, artists: str,
                                     album: str = "", album_art_path: str = None) -> bool:
        """Display a 'Now Playing' screen with track info and album art.

        Args:
            track_name: Song title
            artists: Comma-separated artist names
            album: Album name
            album_art_path: Path to downloaded album art image file
        """
        try:
            logging.info(f"Starting now-playing mode: {track_name} - {artists}")

            display_config = self.display_detector.get_optimal_framebuffer_config()
            width, height = display_config['width'], display_config['height']

            # Check if we need scrolling text
            needs_scrolling = await self._check_if_scrolling_needed(
                track_name, artists, width, height
            )

            # Always show static image immediately first (for fast track switching)
            # Generate static image (responsive display)
            from background_engine.generators.unified import UnifiedBackgroundGenerator
            generator = UnifiedBackgroundGenerator()
            img = generator.create_now_playing_background(
                width, height,
                track_name=track_name,
                artists=artists,
                album=album,
                album_art_path=album_art_path,
            )

            # Save to temp file
            now_playing_path = self.temp_dir / "now_playing.png"
            img.save(str(now_playing_path), compress_level=1)

            # Display static image immediately (fast response)
            self.current_background_path = now_playing_path
            await self._display_current_background()
            self.is_running = True

            # If scrolling is needed, generate video in background and switch to it
            if needs_scrolling:
                asyncio.create_task(self._generate_and_display_scrolling_video(
                    track_name, artists, album, album_art_path, width, height
                ))

            return True

        except Exception as e:
            logging.error(f"Failed to start now-playing mode: {e}")
            return False

    async def _generate_and_display_scrolling_video(self, track_name: str, artists: str,
                                                     album: str, album_art_path: str,
                                                     width: int, height: int) -> None:
        """Generate scrolling video in background and switch to it when ready"""
        try:
            logging.info("Generating scrolling video in background...")
            video_path = await self._generate_scrolling_now_playing_video(
                track_name, artists, album, album_art_path, width, height
            )
            if video_path:
                # Switch to scrolling video
                await self._display_now_playing_video(video_path)
                logging.info("Switched to scrolling video")
        except Exception as e:
            logging.error(f"Failed to generate/display scrolling video: {e}")

    async def _check_if_scrolling_needed(self, track_name: str, artists: str,
                                         width: int, height: int) -> bool:
        """Check if text needs scrolling based on font size and screen width"""
        try:
            from PIL import ImageFont
            from background_engine.config import BackgroundConfig
            config = BackgroundConfig()

            track_font = ImageFont.truetype(config.title_font_path, int(height * 0.12))
            artist_font = ImageFont.truetype(config.subtitle_font_path, int(height * 0.075))

            padding = 80
            max_width = width - (2 * padding)

            track_bbox = track_font.getbbox(track_name)
            artist_bbox = artist_font.getbbox(artists)

            track_w = track_bbox[2] - track_bbox[0]
            artist_w = artist_bbox[2] - artist_bbox[0]

            return track_w > max_width or artist_w > max_width
        except Exception as e:
            logging.warning(f"Failed to check scrolling: {e}")
            return False

    async def _generate_scrolling_now_playing_video(self, track_name: str, artists: str,
                                                     album: str, album_art_path: str,
                                                     width: int, height: int) -> Path:
        """Generate a video with scrolling text using PIL-rendered text for font consistency"""
        try:
            import asyncio
            from PIL import Image, ImageDraw, ImageFont, ImageFilter

            logging.debug(f"Generating scrolling video: track={track_name}, album_art={album_art_path}")
            output_path = self.temp_dir / "now_playing_scroll.mp4"

            # Font sizes
            track_font_size = int(height * 0.12)
            artist_font_size = int(height * 0.075)

            # Text positioning - top left
            text_y_start = 50
            track_y = text_y_start
            artist_y = text_y_start + track_font_size + 30
            padding = 80

            # Load font - use DejaVu Sans (clean, modern sans-serif)
            font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
            track_font = ImageFont.truetype(font_path, track_font_size)
            artist_font = ImageFont.truetype(font_path, artist_font_size)

            # Calculate text dimensions
            max_width = width - (2 * padding)
            track_bbox = track_font.getbbox(track_name)
            artist_bbox = artist_font.getbbox(artists)
            track_width = track_bbox[2] - track_bbox[0]
            artist_width = artist_bbox[2] - artist_bbox[0]

            track_needs_scroll = track_width > max_width
            artist_needs_scroll = artist_width > max_width

            # Calculate canvas width - wide enough for scrolling
            extra_width = max(
                track_width - max_width if track_needs_scroll else 0,
                artist_width - max_width if artist_needs_scroll else 0
            )
            canvas_width = width + extra_width + padding  # Add padding for smooth loop

            # Create background - prepare it at canvas width
            if album_art_path and Path(album_art_path).exists():
                logging.info(f"Loading album art from: {album_art_path}")
                art = Image.open(album_art_path).convert('RGB')
                # Scale to fill screen height
                img_aspect = art.width / art.height
                screen_aspect = width / height
                if img_aspect > screen_aspect:
                    new_height = height
                    new_width = int(art.width * (height / art.height))
                else:
                    new_width = width
                    new_height = int(art.height * (width / art.width))
                art = art.resize((new_width, new_height), Image.Resampling.LANCZOS)
                left = (new_width - width) // 2
                top = (new_height - height) // 2
                art_cropped = art.crop((left, top, left + width, top + height))
                # Blur and darken
                art_cropped = art_cropped.filter(ImageFilter.GaussianBlur(radius=3))
                art_cropped = art_cropped.point(lambda p: int(p * 0.7))

                # Extend to canvas width
                bg_img = Image.new('RGB', (canvas_width, height))
                # Tile the background
                for x in range(0, canvas_width, width):
                    bg_img.paste(art_cropped, (x, 0))
            else:
                # Create dark gradient
                bg_img = Image.new('RGB', (canvas_width, height), (15, 15, 25))

            # Draw text with PIL (ensures consistent font rendering)
            draw = ImageDraw.Draw(bg_img)

            # Draw track name
            draw.text(
                (padding, track_y),
                track_name,
                font=track_font,
                fill='white',
                stroke_width=4,
                stroke_fill='black'
            )

            # Draw artist name
            draw.text(
                (padding, artist_y),
                artists,
                font=artist_font,
                fill='#C8DCFF',
                stroke_width=3,
                stroke_fill='black'
            )

            # Save the wide image
            wide_img_path = self.temp_dir / "now_playing_wide.png"
            bg_img.save(str(wide_img_path))

            # Use ffmpeg to scroll across the wide image
            if track_needs_scroll or artist_needs_scroll:
                # Smooth scrolling using crop filter
                # Scroll from 0 to extra_width+padding and loop
                scroll_distance = extra_width + padding
                scroll_speed = 80  # pixels per second
                scroll_duration = scroll_distance / scroll_speed

                # Crop window scrolls left, then snaps back
                crop_filter = f"crop={width}:{height}:x='mod(t*{scroll_speed},{scroll_distance})':y=0"

                cmd = [
                    "ffmpeg", "-y",
                    "-loop", "1", "-i", str(wide_img_path),
                    "-t", "10",
                    "-vf", crop_filter,
                    "-c:v", "h264_v4l2m2m",
                    "-pix_fmt", "yuv420p",
                    "-b:v", "1.5M",
                    "-preset", "ultrafast",
                    str(output_path)
                ]
            else:
                # No scrolling needed, just encode the static image
                cmd = [
                    "ffmpeg", "-y",
                    "-loop", "1", "-i", str(wide_img_path),
                    "-t", "10",
                    "-c:v", "h264_v4l2m2m",
                    "-pix_fmt", "yuv420p",
                    "-b:v", "1.5M",
                    "-preset", "ultrafast",
                    str(output_path)
                ]

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()

            if proc.returncode == 0:
                logging.info(f"Generated scrolling now-playing video: {output_path}")
                return output_path
            else:
                logging.error(f"Failed to generate scrolling video: {stderr.decode()}")
                return None

        except Exception as e:
            import traceback
            logging.error(f"Failed to generate scrolling video: {e}")
            logging.error(traceback.format_exc())
            return None

    async def _display_now_playing_video(self, video_path: Path) -> bool:
        """Display scrolling now-playing video in loop"""
        try:
            controller = await self.video_pool.get_available_controller()
            if controller:
                await controller.loadfile(str(video_path))
                # Set loop mode to infinite
                await controller.set_property("loop-file", "inf")
                await self.video_pool.release_controller(controller)
                self.current_background_path = video_path
                self.is_running = True
                logging.info("Now-playing scrolling video displayed in loop")
                return True
            else:
                logging.error("No available video controller")
                return False
        except Exception as e:
            logging.error(f"Failed to display scrolling video: {e}")
            return False

    async def stop(self) -> None:
        """Stop background display (video pool handles this automatically)"""
        # No need to do anything - video pool will switch content when needed
        self.is_running = False
        logging.info("Background manager stopped (video pool will handle content switch)")
    
    def is_active(self) -> bool:
        """Check if background display is active"""
        return self.is_running
    
    def get_status(self) -> dict:
        """Get current status information"""
        return {
            "mode": "static",
            "is_running": self.is_running,
            "background_image": self.static_background_image
        }