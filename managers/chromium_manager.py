"""
Chromium Manager

Manages Chromium browser in kiosk mode for web-based display rendering.
Uses cage (Wayland kiosk compositor) for direct DRM/KMS output to HDMI.
"""
import asyncio
import logging
import os
import signal
from typing import Optional


class ChromiumManager:
    """Manages Chromium browser lifecycle in kiosk mode with cage/Wayland"""

    def __init__(self, display_capabilities):
        self.display = display_capabilities
        self.compositor_process: Optional[asyncio.subprocess.Process] = None
        self.current_url: Optional[str] = None

    async def start_kiosk(self, url: str) -> bool:
        """Launch Chromium in kiosk mode via cage Wayland compositor

        Args:
            url: Full URL to display (e.g., "http://localhost:5173/")

        Returns:
            True if successfully started, False otherwise
        """
        try:
            # Stop any existing instance first
            if self.is_running():
                await self.stop()

            # Get display resolution
            display_config = self.display.get_optimal_framebuffer_config()
            width = display_config['width']
            height = display_config['height']

            logging.info(f"Starting Chromium kiosk mode via cage/Wayland: {url} ({width}x{height})")

            # Environment for cage - force DRM backend, strip DISPLAY to prevent X11
            compositor_env = os.environ.copy()
            compositor_env.pop('DISPLAY', None)
            compositor_env.pop('WAYLAND_DISPLAY', None)
            compositor_env.update({
                'WLR_BACKENDS': 'drm',
                'WLR_DRM_DEVICES': '/dev/dri/card1',
                'SEATD_SOCK': '/run/seatd.sock',
                'WLR_RENDERER': 'pixman',  # Software rendering - reliable on Pi
                'XDG_RUNTIME_DIR': os.environ.get('XDG_RUNTIME_DIR', '/run/user/1000'),
                'WLR_LIBINPUT_NO_DEVICES': '1',
            })

            # cage runs a single application fullscreen - perfect for kiosk mode
            # cage -- chromium-browser [flags] [url]
            chromium_args = [
                "chromium-browser",
                "--kiosk",
                "--no-sandbox",
                "--ozone-platform=wayland",
                "--enable-features=UseOzonePlatform",
                "--disable-web-security",
                "--allow-insecure-localhost",
                "--no-first-run",
                "--disable-infobars",
                "--disable-session-crashed-bubble",
                "--disable-translate",
                "--disable-features=TranslateUI",
                "--disable-component-update",
                "--disable-sync",
                "--disable-background-networking",
                "--disable-default-apps",
                "--disable-extensions",
                "--noerrdialogs",
                "--disable-notifications",
                "--password-store=basic",
                "--disable-popup-blocking",
                "--user-data-dir=/tmp/chromium-hsg-canvas",
                "--start-fullscreen",
                url,
            ]

            # Start cage compositor with Chromium as its application
            log_file = open("/tmp/cage-kiosk.log", "w")
            logging.info("Starting cage Wayland kiosk compositor")
            self.compositor_process = await asyncio.create_subprocess_exec(
                "cage", "--", *chromium_args,
                env=compositor_env,
                stdout=log_file,
                stderr=log_file,
                preexec_fn=os.setsid
            )
            log_file.close()

            # Wait for compositor and Chromium to initialize
            await asyncio.sleep(5.0)

            if self.compositor_process and self.compositor_process.returncode is not None:
                try:
                    with open("/tmp/cage-kiosk.log", "r") as f:
                        log_content = f.read()
                    logging.error(f"cage failed to start: {log_content}")
                except Exception:
                    logging.error("cage failed to start (no log available)")
                return False

            self.current_url = url
            logging.info(f"Chromium kiosk mode started via cage (PID: {self.compositor_process.pid})")
            return True

        except FileNotFoundError as e:
            logging.error(f"Required binary not found: {e}")
            logging.error("Please install: sudo apt-get install cage chromium-browser")
            await self._cleanup_processes()
            return False
        except Exception as e:
            logging.error(f"Failed to start Chromium kiosk mode: {e}")
            import traceback
            logging.error(traceback.format_exc())
            await self._cleanup_processes()
            return False

    async def stop(self):
        """Stop compositor and Chromium processes"""
        if not self.is_running():
            return

        logging.info("Stopping Chromium kiosk mode")
        await self._cleanup_processes()
        self.current_url = None
        logging.info("Chromium kiosk mode stopped")

    async def _cleanup_processes(self):
        """Clean up compositor process (kills Chromium too since it's a child)"""
        if self.compositor_process:
            try:
                if self.compositor_process.pid:
                    try:
                        os.killpg(os.getpgid(self.compositor_process.pid), signal.SIGTERM)
                        logging.debug("Sent SIGTERM to compositor process group")
                    except ProcessLookupError:
                        pass

                try:
                    await asyncio.wait_for(self.compositor_process.wait(), timeout=3.0)
                except asyncio.TimeoutError:
                    try:
                        os.killpg(os.getpgid(self.compositor_process.pid), signal.SIGKILL)
                        logging.debug("Sent SIGKILL to compositor process group")
                    except ProcessLookupError:
                        pass

                logging.debug("Compositor process cleaned up")
            except Exception as e:
                logging.warning(f"Error cleaning up compositor process: {e}")
            finally:
                self.compositor_process = None

    def is_running(self) -> bool:
        """Check if compositor/Chromium is currently active"""
        if not self.compositor_process:
            return False

        if self.compositor_process.returncode is not None:
            logging.debug("Compositor process has terminated")
            self.compositor_process = None
            self.current_url = None
            return False

        return True

    def get_status(self) -> dict:
        """Get current Chromium status"""
        return {
            "is_running": self.is_running(),
            "current_url": self.current_url,
            "compositor_pid": self.compositor_process.pid if self.compositor_process else None,
        }
