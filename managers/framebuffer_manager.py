"""
Framebuffer Manager

Direct framebuffer management for seamless background display with optimal resolution.
"""
import logging
import mmap
from typing import Tuple

import numpy as np
from PIL import Image

from managers.display_detector import DisplayCapabilityDetector


class FramebufferManager:
    """Direct framebuffer management for seamless background display with optimal resolution"""

    def __init__(self, display_detector: DisplayCapabilityDetector = None):
        self.display_detector = display_detector
        self.fb_device = "/dev/fb0"

        # Get optimal configuration from display detector
        if display_detector:
            optimal_config = display_detector.get_optimal_framebuffer_config()
            self.target_width = optimal_config['width']
            self.target_height = optimal_config['height']
        else:
            self.target_width = 1920
            self.target_height = 1080

        # Actual framebuffer parameters (may differ from target)
        self.fb_width = 640  # will be updated by _get_fb_info
        self.fb_height = 480  # will be updated by _get_fb_info
        self.fb_bpp = 16  # bits per pixel
        self.fb_bytes_per_pixel = self.fb_bpp // 8
        self.fb_size = self.fb_width * self.fb_height * self.fb_bytes_per_pixel
        self.fb_format = 'RGB565'  # 5 bits red, 6 bits green, 5 bits blue

        # Memory management
        self.fb_file = None
        self.fb_mmap = None
        self.fb_array = None
        self.is_available = False

        # Performance optimization - pre-calculate scaling parameters
        self.scale_x = 1.0
        self.scale_y = 1.0

    def initialize(self):
        """Initialize framebuffer (non-async for compatibility)"""
        self._initialize_framebuffer()

    def _initialize_framebuffer(self):
        """Initialize framebuffer access and memory mapping with optimal resolution awareness"""
        try:
            # Get actual framebuffer info
            self._get_fb_info()

            # Calculate scaling parameters for optimal resolution rendering
            self.scale_x = self.fb_width / self.target_width
            self.scale_y = self.fb_height / self.target_height

            # Open framebuffer device
            self.fb_file = open(self.fb_device, 'r+b')

            # Create memory map
            self.fb_mmap = mmap.mmap(self.fb_file.fileno(), self.fb_size)

            # Create numpy array view of framebuffer
            if self.fb_bpp == 16:
                self.fb_array = np.frombuffer(self.fb_mmap, dtype=np.uint16).reshape((self.fb_height, self.fb_width))
            else:
                self.fb_array = np.frombuffer(self.fb_mmap, dtype=np.uint32).reshape((self.fb_height, self.fb_width))

            self.is_available = True
            logging.info(f"Framebuffer initialized: {self.fb_width}x{self.fb_height}, {self.fb_bpp}bpp")
            logging.info(f"Target resolution: {self.target_width}x{self.target_height}")
            logging.info(f"Scaling factors: {self.scale_x:.3f}x, {self.scale_y:.3f}y")

        except Exception as e:
            logging.warning(f"Framebuffer not available: {e}")
            self.is_available = False

    def _get_fb_info(self):
        """Get framebuffer information from system"""
        try:
            # Read virtual size
            with open('/sys/class/graphics/fb0/virtual_size', 'r') as f:
                size_str = f.read().strip()
                self.fb_width, self.fb_height = map(int, size_str.split(','))

            # Read bits per pixel
            with open('/sys/class/graphics/fb0/bits_per_pixel', 'r') as f:
                self.fb_bpp = int(f.read().strip())

            self.fb_bytes_per_pixel = self.fb_bpp // 8
            self.fb_size = self.fb_width * self.fb_height * self.fb_bytes_per_pixel

        except Exception as e:
            logging.warning(f"Could not read framebuffer info, using defaults: {e}")

    def _rgb_to_rgb565(self, r: int, g: int, b: int) -> int:
        """Convert RGB888 to RGB565 format"""
        # Convert 8-bit values to appropriate bit ranges
        r5 = (r >> 3) & 0x1F  # 5 bits
        g6 = (g >> 2) & 0x3F  # 6 bits
        b5 = (b >> 3) & 0x1F  # 5 bits

        # Pack into 16-bit value: RRRRRGGGGGGBBBBB
        return (r5 << 11) | (g6 << 5) | b5

    def _resize_image_preserve_aspect(self, img: Image.Image, target_width: int, target_height: int) -> Image.Image:
        """Resize image to maximize screen usage, only adding minimal borders where aspect ratio requires it"""
        orig_width, orig_height = img.size

        # If image already matches target resolution exactly, return as-is
        if orig_width == target_width and orig_height == target_height:
            return img

        # Calculate aspect ratios
        target_aspect = target_width / target_height
        img_aspect = orig_width / orig_height

        # Scale to fill maximum space while preserving aspect ratio
        if img_aspect > target_aspect:
            # Image is wider - fit to width, add small borders on top/bottom
            new_width = target_width
            new_height = int(target_width / img_aspect)
        else:
            # Image is taller - fit to height, add small borders on left/right
            new_height = target_height
            new_width = int(target_height * img_aspect)

        # Resize image to calculated dimensions
        scaled_img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

        # If scaled image matches target exactly, return it
        if new_width == target_width and new_height == target_height:
            return scaled_img

        # Create canvas with black borders only where needed
        canvas = Image.new('RGB', (target_width, target_height), (0, 0, 0))
        x_offset = (target_width - new_width) // 2
        y_offset = (target_height - new_height) // 2
        canvas.paste(scaled_img, (x_offset, y_offset))

        return canvas

    def display_image(self, image_path: str) -> bool:
        """Display an image on the framebuffer"""
        if not self.is_available:
            return False

        try:
            # Load and resize image
            with Image.open(image_path) as img:
                # Convert to RGB if needed
                if img.mode != 'RGB':
                    img = img.convert('RGB')

                # Resize to framebuffer dimensions while preserving aspect ratio
                img_resized = self._resize_image_preserve_aspect(img, self.fb_width, self.fb_height)

                # Convert to numpy array
                img_array = np.array(img_resized)

                # Convert to framebuffer format using vectorized operations
                if self.fb_bpp == 16:
                    # Convert RGB888 to RGB565 efficiently
                    r = (img_array[:, :, 0] >> 3).astype(np.uint16)
                    g = (img_array[:, :, 1] >> 2).astype(np.uint16)
                    b = (img_array[:, :, 2] >> 3).astype(np.uint16)
                    fb_data = (r << 11) | (g << 5) | b
                else:
                    # Assume 32-bit RGBA
                    r = img_array[:, :, 0].astype(np.uint32)
                    g = img_array[:, :, 1].astype(np.uint32)
                    b = img_array[:, :, 2].astype(np.uint32)
                    fb_data = (0xFF << 24) | (r << 16) | (g << 8) | b

                # Write to framebuffer
                np.copyto(self.fb_array, fb_data)
                self.fb_mmap.flush()

                logging.info(f"Successfully displayed image on framebuffer: {image_path}")
                return True

        except Exception as e:
            logging.error(f"Failed to display image on framebuffer: {e}")
            return False

    def clear_screen(self, color: Tuple[int, int, int] = (0, 0, 0)) -> bool:
        """Clear framebuffer to solid color"""
        if not self.is_available:
            return False

        try:
            if self.fb_bpp == 16:
                color_value = self._rgb_to_rgb565(color[0], color[1], color[2])
            else:
                color_value = (0xFF << 24) | (color[0] << 16) | (color[1] << 8) | color[2]

            self.fb_array.fill(color_value)
            self.fb_mmap.flush()
            return True

        except Exception as e:
            logging.error(f"Failed to clear framebuffer: {e}")
            return False

    def cleanup(self):
        """Clean up framebuffer resources"""
        try:
            # Clear NumPy array references to allow mmap to close
            if hasattr(self, 'fb_array') and self.fb_array is not None:
                # Explicitly delete array reference
                del self.fb_array
                self.fb_array = None

            # Also clear any other potential NumPy array references
            if hasattr(self, 'write_array') and self.write_array is not None:
                del self.write_array
                self.write_array = None

            # Force garbage collection to ensure NumPy releases references
            import gc
            gc.collect()

            # Sync buffer before closing
            if hasattr(self, 'fb_mmap') and self.fb_mmap:
                try:
                    self.fb_mmap.flush()
                except Exception as flush_error:
                    logging.warning(f"Failed to flush framebuffer: {flush_error}")

                # Close memory map
                self.fb_mmap.close()
                self.fb_mmap = None

            # Close file handle
            if hasattr(self, 'fb_file') and self.fb_file:
                self.fb_file.close()
                self.fb_file = None

            self.is_available = False
            logging.debug("Framebuffer resources cleaned up successfully")

        except Exception as e:
            logging.error(f"Error cleaning up framebuffer: {e}")
            # Continue cleanup attempt even if some steps fail
            self.is_available = False

    def is_resource_active(self) -> bool:
        """Check if framebuffer resources are actively initialized"""
        return (hasattr(self, 'fb_mmap') and self.fb_mmap is not None and
                hasattr(self, 'fb_file') and self.fb_file is not None and
                hasattr(self, 'fb_array') and self.fb_array is not None)
