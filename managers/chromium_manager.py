"""
Chromium Manager

Manages Chromium browser in kiosk mode for web-based display rendering.
Uses cage (Wayland kiosk compositor) for direct DRM/KMS output to HDMI.
"""
import asyncio
import json
import logging
import os
import signal
import subprocess
from typing import Optional

import aiohttp


class ChromiumManager:
    """Manages Chromium browser lifecycle in kiosk mode with cage/Wayland"""

    CDP_PORT = 9222

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
            # HDMI-A-2 is disabled at kernel level (video=HDMI-A-2:d in cmdline.txt)
            # so cage only sees HDMI-A-1 and renders fullscreen on it.
            compositor_env.update({
                'WLR_BACKENDS': 'drm',
                'WLR_DRM_DEVICES': '/dev/dri/card1',
                'SEATD_SOCK': '/run/seatd.sock',
                'WLR_RENDERER': 'gles2',  # GPU-accelerated via v3d
                'XDG_RUNTIME_DIR': os.environ.get('XDG_RUNTIME_DIR', '/run/user/1000'),
                'WLR_LIBINPUT_NO_DEVICES': '1',
            })

            # cage runs a single application fullscreen - perfect for kiosk mode
            # cage -- chromium-browser [flags] [url]
            # Only zoom external sites — our React app handles its own layout
            is_local = url.startswith("http://127.0.0.1") or url.startswith("http://localhost")

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
                "--autoplay-policy=no-user-gesture-required",
                f"--remote-debugging-port={self.CDP_PORT}",
            ]

            if not is_local:
                chromium_args.append("--force-device-scale-factor=1.5")

            chromium_args.append(url)

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

    async def _get_cdp_ws_url(self) -> Optional[str]:
        """Get the Chrome DevTools Protocol WebSocket URL for the active page"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"http://127.0.0.1:{self.CDP_PORT}/json",
                    timeout=aiohttp.ClientTimeout(total=2)
                ) as resp:
                    if resp.status == 200:
                        targets = await resp.json()
                        for target in targets:
                            if target.get("type") == "page":
                                return target.get("webSocketDebuggerUrl")
        except Exception as e:
            logging.warning(f"Failed to get CDP WebSocket URL: {e}")
        return None

    async def _cdp_command(self, method: str, params: Optional[dict] = None) -> bool:
        """Send a command to Chromium via Chrome DevTools Protocol"""
        ws_url = await self._get_cdp_ws_url()
        if not ws_url:
            logging.error("No CDP target available — Chromium may not be running")
            return False

        try:
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(ws_url, timeout=5) as ws:
                    msg = {"id": 1, "method": method}
                    if params:
                        msg["params"] = params
                    await ws.send_json(msg)
                    resp = await asyncio.wait_for(ws.receive_json(), timeout=5)
                    if "error" in resp:
                        logging.error(f"CDP {method} failed: {resp['error']}")
                        return False
                    return True
        except Exception as e:
            logging.error(f"CDP command {method} failed: {e}")
            return False

    async def reload_page(self) -> bool:
        """Reload the current page via Chrome DevTools Protocol"""
        if not self.is_running():
            logging.warning("Cannot reload — Chromium is not running")
            return False

        logging.info("Reloading Chromium page via CDP")
        return await self._cdp_command("Page.reload", {"ignoreCache": True})

    async def navigate(self, url: str) -> bool:
        """Navigate Chromium to a new URL via Chrome DevTools Protocol"""
        if not self.is_running():
            logging.warning("Cannot navigate — Chromium is not running")
            return False

        logging.info(f"Navigating Chromium to {url} via CDP")
        success = await self._cdp_command("Page.navigate", {"url": url})
        if success:
            self.current_url = url
        return success

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

    def _has_zombie_children(self) -> bool:
        """Check if the Chromium process tree has zombie (defunct) children.

        A zombie GPU process means Chromium can't render and needs a restart.
        """
        if not self.compositor_process or not self.compositor_process.pid:
            return False

        try:
            result = subprocess.run(
                ["ps", "--ppid", str(self.compositor_process.pid), "-o", "pid="],
                capture_output=True, text=True, timeout=5
            )
            # Get all descendant PIDs (cage -> chromium -> children)
            pids = result.stdout.split()
            for pid in pids:
                pid = pid.strip()
                if not pid:
                    continue
                # Check children of each direct child too
                result2 = subprocess.run(
                    ["ps", "--ppid", pid, "-o", "pid=,stat="],
                    capture_output=True, text=True, timeout=5
                )
                for line in result2.stdout.strip().split('\n'):
                    parts = line.split()
                    if len(parts) >= 2 and 'Z' in parts[1]:
                        logging.warning(f"Zombie child process detected: PID {parts[0]} (stat={parts[1]})")
                        return True
        except Exception as e:
            logging.warning(f"Error checking for zombie children: {e}")

        return False

    async def check_health(self) -> bool:
        """Check if Chromium is healthy. Returns True if healthy, False if restart needed."""
        if not self.is_running():
            return False

        if self._has_zombie_children():
            logging.error("Chromium has zombie child processes (GPU crash) — restarting")
            url = self.current_url
            await self.stop()
            if url:
                await self.start_kiosk(url)
            return False

        return True

    def get_status(self) -> dict:
        """Get current Chromium status"""
        return {
            "is_running": self.is_running(),
            "current_url": self.current_url,
            "compositor_pid": self.compositor_process.pid if self.compositor_process else None,
        }
