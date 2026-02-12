"""
Chromium Manager

Manages Chromium browser in kiosk mode for web-based display rendering.
Uses X11 with modesetting driver for direct DRM/KMS output to HDMI.
"""
import asyncio
import logging
import os
import signal
from typing import Optional
from pathlib import Path


class ChromiumManager:
    """Manages Chromium browser lifecycle in kiosk mode with X11/modesetting"""

    def __init__(self, display_capabilities):
        self.display = display_capabilities
        self.chromium_process: Optional[asyncio.subprocess.Process] = None
        self.xorg_process: Optional[asyncio.subprocess.Process] = None
        self.current_url: Optional[str] = None
        self.display_num = ":1"  # X11 display number
        self.xorg_log = "/tmp/Xorg.1.log"

    async def start_kiosk(self, url: str) -> bool:
        """Launch Chromium in kiosk mode via X11/modesetting

        Args:
            url: Full URL to display (e.g., "http://localhost:80/now-playing")

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

            logging.info(f"Starting Chromium kiosk mode via X11: {url} ({width}x{height})")

            # Create minimal xorg.conf for modesetting with DRM
            # Use standard VESA modes that monitors support
            xorg_conf = f"""
Section "Device"
    Identifier "Card0"
    Driver "modesetting"
    Option "kmsdev" "/dev/dri/card1"
EndSection

Section "Monitor"
    Identifier "Monitor0"
    Option "PreferredMode" "1920x1080"
EndSection

Section "Screen"
    Identifier "Screen0"
    Device "Card0"
    Monitor "Monitor0"
    DefaultDepth 24
    SubSection "Display"
        Depth 24
        Modes "1920x1080" "1280x720" "1024x768"
    EndSubSection
EndSection
"""
            xorg_conf_path = "/tmp/xorg-kiosk.conf"
            with open(xorg_conf_path, 'w') as f:
                f.write(xorg_conf)

            # Start X server with modesetting driver (outputs to HDMI)
            # Need sudo for VT access
            logging.info(f"Starting X server on {self.display_num} with modesetting driver (via sudo)")
            self.xorg_process = await asyncio.create_subprocess_exec(
                "sudo",
                "X",
                self.display_num,
                "-config", xorg_conf_path,
                "-logfile", self.xorg_log,
                "-nolisten", "tcp",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
                preexec_fn=os.setsid
            )

            # Wait for X server to initialize
            await asyncio.sleep(2.0)

            if self.xorg_process and self.xorg_process.returncode is not None:
                stderr = await self.xorg_process.stderr.read()
                logging.error(f"X server failed to start: {stderr.decode()}")
                # Read X log for more details
                if os.path.exists(self.xorg_log):
                    with open(self.xorg_log) as f:
                        log_tail = f.readlines()[-20:]
                        logging.error(f"X server log:\n{''.join(log_tail)}")
                return False

            # Start unclutter to hide cursor
            logging.info("Starting unclutter to hide cursor")
            unclutter_env = os.environ.copy()
            unclutter_env['DISPLAY'] = self.display_num
            await asyncio.create_subprocess_exec(
                "unclutter", "-idle", "0.1", "-root",
                env=unclutter_env,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL
            )

            # Start Chromium on X server
            logging.info(f"Starting Chromium on display {self.display_num}")
            chromium_env = os.environ.copy()
            chromium_env['DISPLAY'] = self.display_num

            self.chromium_process = await asyncio.create_subprocess_exec(
                "chromium-browser",
                "--kiosk",
                "--no-sandbox",  # Disable sandbox to allow network access
                "--disable-web-security",  # Disable web security for local access
                "--allow-insecure-localhost",  # Allow localhost connections
                "--no-first-run",
                "--disable-infobars",
                "--disable-session-crashed-bubble",
                "--disable-translate",
                "--disable-features=TranslateUI",
                "--disable-component-update",
                "--disable-sync",  # Disable sync to avoid profile errors
                "--disable-background-networking",  # Reduce background activity
                "--disable-default-apps",  # No default apps
                "--disable-extensions",  # No extensions
                "--noerrdialogs",  # Suppress error dialogs
                "--disable-notifications",  # No notifications
                "--password-store=basic",  # Avoid keyring errors
                "--disable-popup-blocking",  # No popup blockers
                "--user-data-dir=/tmp/chromium-hsg-canvas",
                f"--window-size={width},{height}",
                "--window-position=0,0",
                "--start-fullscreen",
                "--kiosk-printing",
                url,
                env=chromium_env,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
                preexec_fn=os.setsid
            )

            # Wait to check if Chromium started successfully
            await asyncio.sleep(2.0)

            if self.chromium_process and self.chromium_process.returncode is not None:
                stderr = await self.chromium_process.stderr.read()
                logging.error(f"Chromium failed to start: {stderr.decode()}")
                await self._cleanup_xorg()
                return False

            self.current_url = url
            logging.info(f"Chromium kiosk mode started successfully (PID: {self.chromium_process.pid})")
            logging.info(f"X server running on {self.display_num} (PID: {self.xorg_process.pid})")
            return True

        except FileNotFoundError as e:
            logging.error(f"Required binary not found: {e}")
            logging.error("Please install: sudo apt-get install xserver-xorg chromium-browser")
            await self._cleanup_processes()
            return False
        except Exception as e:
            logging.error(f"Failed to start Chromium kiosk mode: {e}")
            import traceback
            logging.error(traceback.format_exc())
            await self._cleanup_processes()
            return False

    async def stop(self):
        """Stop Chromium and X server processes"""
        if not self.is_running():
            return

        logging.info("Stopping Chromium kiosk mode")
        await self._cleanup_processes()
        self.current_url = None
        logging.info("Chromium kiosk mode stopped")

    async def _cleanup_processes(self):
        """Clean up Chromium and X server processes"""
        await self._cleanup_chromium()
        await self._cleanup_xorg()

    async def _cleanup_chromium(self):
        """Stop Chromium process"""
        if self.chromium_process:
            try:
                # Kill process group (Chromium spawns multiple child processes)
                if self.chromium_process.pid:
                    try:
                        os.killpg(os.getpgid(self.chromium_process.pid), signal.SIGTERM)
                        logging.debug("Sent SIGTERM to Chromium process group")
                    except ProcessLookupError:
                        pass  # Already dead

                # Wait for graceful shutdown with timeout
                try:
                    await asyncio.wait_for(self.chromium_process.wait(), timeout=3.0)
                except asyncio.TimeoutError:
                    # Force kill if still running
                    try:
                        os.killpg(os.getpgid(self.chromium_process.pid), signal.SIGKILL)
                        logging.debug("Sent SIGKILL to Chromium process group")
                    except ProcessLookupError:
                        pass

                logging.debug("Chromium process cleaned up")
            except Exception as e:
                logging.warning(f"Error cleaning up Chromium process: {e}")
            finally:
                self.chromium_process = None

    async def _cleanup_xorg(self):
        """Stop X server process"""
        if self.xorg_process:
            try:
                # Kill process group
                if self.xorg_process.pid:
                    try:
                        os.killpg(os.getpgid(self.xorg_process.pid), signal.SIGTERM)
                        logging.debug("Sent SIGTERM to X server process group")
                    except ProcessLookupError:
                        pass

                # Wait for graceful shutdown with timeout
                try:
                    await asyncio.wait_for(self.xorg_process.wait(), timeout=2.0)
                except asyncio.TimeoutError:
                    try:
                        os.killpg(os.getpgid(self.xorg_process.pid), signal.SIGKILL)
                        logging.debug("Sent SIGKILL to X server process group")
                    except ProcessLookupError:
                        pass

                logging.debug("X server process cleaned up")
            except Exception as e:
                logging.warning(f"Error cleaning up X server process: {e}")
            finally:
                self.xorg_process = None

    def is_running(self) -> bool:
        """Check if Chromium is currently active"""
        if not self.chromium_process:
            return False

        # Check if process is still alive
        if self.chromium_process.returncode is not None:
            logging.debug("Chromium process has terminated")
            self.chromium_process = None
            self.xorg_process = None
            self.current_url = None
            return False

        return True

    async def navigate_to(self, url: str) -> bool:
        """Navigate to a new URL without restarting Chromium

        Args:
            url: Full URL to navigate to (e.g., "http://localhost:5173/now-playing")

        Returns:
            True if navigation command sent successfully, False otherwise
        """
        if not self.is_running():
            logging.warning("Cannot navigate - Chromium is not running")
            return False

        try:
            logging.info(f"Navigating Chromium to: {url}")

            # Use xdotool to control Chromium
            # Set DISPLAY environment variable for xdotool
            env = os.environ.copy()
            env['DISPLAY'] = self.display_num

            # Find Chromium window
            proc = await asyncio.create_subprocess_exec(
                "xdotool", "search", "--class", "chromium",
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()

            if proc.returncode != 0:
                logging.error(f"Could not find Chromium window: {stderr.decode()}")
                return False

            window_id = stdout.decode().strip().split('\n')[0]

            # Focus window, open address bar, type URL, press Enter
            commands = [
                ["xdotool", "windowactivate", "--sync", window_id],
                ["xdotool", "key", "--delay", "100", "ctrl+l"],  # Focus address bar
                ["xdotool", "key", "--delay", "100", "ctrl+a"],  # Select all
                ["xdotool", "type", "--delay", "50", url],       # Type URL
                ["xdotool", "key", "Return"]                      # Navigate
            ]

            for cmd in commands:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    env=env,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.PIPE
                )
                await proc.wait()
                await asyncio.sleep(0.1)  # Small delay between commands

            self.current_url = url
            logging.info(f"Navigation command sent successfully")
            return True

        except FileNotFoundError:
            logging.error("xdotool not found - please install: sudo apt-get install xdotool")
            return False
        except Exception as e:
            logging.error(f"Failed to navigate Chromium: {e}")
            import traceback
            logging.error(traceback.format_exc())
            return False

    def get_status(self) -> dict:
        """Get current Chromium status"""
        return {
            "is_running": self.is_running(),
            "current_url": self.current_url,
            "display": self.display_num if self.is_running() else None,
            "chromium_pid": self.chromium_process.pid if self.chromium_process else None,
            "xorg_pid": self.xorg_process.pid if self.xorg_process else None,
        }
