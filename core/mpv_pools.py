"""
MPV Process Pools

Manages pools of mpv processes with IPC control for audio and video playback.
Includes automatic health checking and crash recovery.
"""
import asyncio
import logging
import os
import subprocess
import time
from datetime import datetime
from typing import Optional, Dict

from core.mpv_controller import MPVController
from config import AUDIO_DEVICE, SOCKET_DIR


class MPVProcessPool:
    """Generic base class for managing a pool of mpv processes with IPC control"""

    def __init__(self, pool_name: str = "mpv", pool_size: int = 2, socket_dir: str = SOCKET_DIR):
        """
        Initialize MPV process pool

        Args:
            pool_name: Name of the pool (used for logging and socket naming)
            pool_size: Number of processes in the pool
            socket_dir: Directory for IPC sockets
        """
        self.pool_name = pool_name
        self.pool_size = pool_size
        self.processes: Dict[int, subprocess.Popen] = {}
        self.controllers: Dict[int, MPVController] = {}
        self.process_status: Dict[int, Dict] = {}
        self.socket_dir = socket_dir

    async def initialize(self) -> bool:
        """Initialize the pool with configured number of mpv processes"""
        try:
            logging.info(f"Starting {self.pool_name} pool initialization ({self.pool_size} processes)...")
            # Ensure socket directory exists
            os.makedirs(self.socket_dir, exist_ok=True)
            logging.info(f"Created socket directory: {self.socket_dir}")

            for process_id in range(1, self.pool_size + 1):
                logging.info(f"Starting {self.pool_name} process {process_id}...")
                success = await self._start_process(process_id)
                if not success:
                    logging.error(f"Failed to start {self.pool_name} process {process_id}")
                    await self.cleanup()
                    return False
                logging.info(f"Successfully started {self.pool_name} process {process_id}")

            logging.info(f"{self.pool_name} pool initialized with {self.pool_size} processes")
            return True

        except Exception as e:
            logging.error(f"Failed to initialize {self.pool_name} pool: {e}")
            import traceback
            traceback.print_exc()
            await self.cleanup()
            return False

    async def _start_process(self, process_id: int) -> bool:
        """Start a single mpv process with IPC"""
        try:
            socket_path = f"{self.socket_dir}/{self.pool_name}-pool-{process_id}"

            # Remove existing socket if it exists
            if os.path.exists(socket_path):
                os.remove(socket_path)

            # Get mpv command from subclass implementation
            cmd = self._get_mpv_command(socket_path)

            # Start mpv process
            env = os.environ.copy()
            env.update({
                'DRM_DEVICE': '/dev/dri/card0',
                'DRM_CONNECTOR': 'HDMI-A-1'
            })

            process = subprocess.Popen(
                cmd,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                preexec_fn=os.setsid
            )

            # Wait for socket to be created
            await self._wait_for_socket(socket_path)

            # Create controller and connect
            controller = MPVController(socket_path, process_id)
            connected = await controller.connect()

            if not connected:
                process.terminate()
                return False

            # Store process and controller
            self.processes[process_id] = process
            self.controllers[process_id] = controller
            self.process_status[process_id] = {
                "status": "idle",
                "content_type": None,
                "stream_key": None
            }

            # Set up initial property observations
            await controller.observe_property("time-pos")
            await controller.observe_property("duration")
            await controller.observe_property("volume")
            await controller.observe_property("pause")
            await controller.observe_property("speed")

            logging.info(f"MPV process {process_id} started and connected")
            return True

        except Exception as e:
            logging.error(f"Failed to start MPV process {process_id}: {e}")
            return False

    async def _restart_process(self, process_id: int) -> bool:
        """Restart a dead MPV process"""
        try:
            # Clean up old process and controller
            if process_id in self.processes:
                try:
                    self.processes[process_id].terminate()
                except:
                    pass
                del self.processes[process_id]

            if process_id in self.controllers:
                try:
                    self.controllers[process_id].disconnect()
                except:
                    pass
                del self.controllers[process_id]

            # Remove old socket file
            socket_path = f"{self.socket_dir}/{self.pool_name}-pool-{process_id}"
            if os.path.exists(socket_path):
                os.remove(socket_path)

            # Start new process
            return await self._start_process(process_id)

        except Exception as e:
            logging.error(f"Failed to restart {self.pool_name} process {process_id}: {e}")
            return False

    def _get_mpv_command(self, socket_path: str) -> list:
        """Get mpv command with IPC enabled. Override in subclasses for specific configurations."""
        raise NotImplementedError("Subclasses must implement _get_mpv_command()")

    async def _wait_for_socket(self, socket_path: str, timeout: float = 10.0) -> bool:
        """Wait for mpv to create the IPC socket"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            if os.path.exists(socket_path):
                # Socket exists, wait a bit more for mpv to be ready
                await asyncio.sleep(0.5)
                return True
            await asyncio.sleep(0.1)
        return False

    def get_available_process(self) -> Optional[int]:
        """Get an available process ID, prefer idle processes"""
        # Check if pool is initialized
        if not self.processes:
            logging.warning("MPV pool not initialized")
            return None

        # First, look for idle processes
        for process_id, status in self.process_status.items():
            if status["status"] == "idle":
                return process_id

        # If no idle processes, return None (all busy)
        return None

    async def get_available_controller(self, retry_with_health_check: bool = True) -> Optional[MPVController]:
        """Get an available MPVController with automatic recovery

        Args:
            retry_with_health_check: If True, will trigger a health check and retry if no controller available

        Returns:
            MPVController if available, None otherwise
        """
        # Check if pool is initialized
        if not self.processes:
            logging.warning("MPV pool not initialized")
            return None

        # First pass: look for idle processes
        for process_id, status in self.process_status.items():
            if status["status"] == "idle":
                controller = self.controllers.get(process_id)
                if controller:
                    # Check if the process is actually alive
                    process = self.processes.get(process_id)
                    if process and process.poll() is None:
                        # Process is alive, mark as in use
                        controller.in_use = True
                        self.process_status[process_id]["status"] = "busy"
                        return controller
                    else:
                        # Process is dead, restart it
                        logging.warning(f"MPV process {process_id} is dead, restarting")
                        if await self._restart_process(process_id):
                            controller = self.controllers.get(process_id)
                            if controller:
                                controller.in_use = True
                                self.process_status[process_id]["status"] = "busy"
                                return controller

        # No idle processes found - if retry is enabled, run health check and try again
        if retry_with_health_check:
            logging.warning("No available MPV controllers, running health check and retrying...")
            health_report = await self.health_check()

            # If we restarted any processes, try again
            if health_report["restarted"] > 0:
                logging.info(f"Health check restarted {health_report['restarted']} processes, retrying allocation...")

                # Wait a moment for processes to stabilize
                await asyncio.sleep(1)

                # Retry (but don't recurse - pass False to avoid infinite loop)
                return await self.get_available_controller(retry_with_health_check=False)

        # If no idle processes after all attempts, return None (all busy or failed)
        logging.error(f"No MPV controllers available. Status: {len([s for s in self.process_status.values() if s['status'] == 'busy'])} busy, "
                     f"{len([s for s in self.process_status.values() if s['status'] == 'idle'])} idle")
        return None

    async def release_controller(self, controller: MPVController):
        """Release a controller back to idle state"""
        controller.in_use = False
        if controller.process_id in self.process_status:
            self.process_status[controller.process_id]["status"] = "idle"
            logging.info(f"Released MPV controller {controller.process_id} back to pool")

    async def allocate_process(self, content_type: str, stream_key: str) -> Optional[int]:
        """Allocate a process for content playback"""
        process_id = self.get_available_process()
        if process_id is None:
            return None

        self.process_status[process_id] = {
            "status": "busy",
            "content_type": content_type,
            "stream_key": stream_key
        }

        logging.info(f"Allocated MPV process {process_id} for {content_type}: {stream_key}")
        return process_id

    async def release_process(self, process_id: int):
        """Release a process back to idle state"""
        if process_id in self.process_status:
            # Stop current playback
            controller = self.controllers.get(process_id)
            if controller:
                await controller.send_command(["stop"])

            self.process_status[process_id] = {
                "status": "idle",
                "content_type": None,
                "stream_key": None
            }

            logging.info(f"Released MPV process {process_id} to idle state")

    def get_controller(self, process_id: int) -> Optional[MPVController]:
        """Get the controller for a specific process"""
        return self.controllers.get(process_id)

    def get_process_status(self) -> dict:
        """Get status of all processes"""
        status = {}
        for process_id in range(1, self.pool_size + 1):
            if process_id in self.processes:
                process = self.processes[process_id]
                controller = self.controllers[process_id]
                status[process_id] = {
                    "running": process.poll() is None,
                    "connected": controller.connected,
                    **self.process_status[process_id]
                }
            else:
                status[process_id] = {"running": False, "connected": False}
        return status

    async def cleanup(self):
        """Clean up all processes and connections"""
        for process_id in list(self.controllers.keys()):
            controller = self.controllers[process_id]
            try:
                await controller.quit()
                controller.disconnect()
            except:
                pass

        for process_id in list(self.processes.keys()):
            process = self.processes[process_id]
            try:
                process.terminate()
                process.wait(timeout=5)
            except:
                try:
                    process.kill()
                except:
                    pass

        # Clean up socket files
        for process_id in range(1, self.pool_size + 1):
            socket_path = f"{self.socket_dir}/{self.pool_name}-pool-{process_id}"
            if os.path.exists(socket_path):
                os.remove(socket_path)

        self.processes.clear()
        self.controllers.clear()
        self.process_status.clear()

        logging.info(f"{self.pool_name} pool cleaned up")

    async def health_check(self) -> dict:
        """Check health of all MPV processes and restart dead ones"""
        health_report = {
            "checked_at": datetime.now().isoformat(),
            "total_processes": self.pool_size,
            "healthy": 0,
            "restarted": 0,
            "failed": 0,
            "processes": {}
        }

        for process_id in range(1, self.pool_size + 1):
            process = self.processes.get(process_id)
            controller = self.controllers.get(process_id)

            # Check if process exists and is alive
            if not process or process.poll() is not None:
                # Process is dead, attempt restart
                logging.warning(f"MPV process {process_id} is dead, attempting restart...")
                try:
                    success = await self._restart_process(process_id)
                    if success:
                        health_report["restarted"] += 1
                        health_report["processes"][process_id] = "restarted"
                        logging.info(f"Successfully restarted MPV process {process_id}")
                    else:
                        health_report["failed"] += 1
                        health_report["processes"][process_id] = "restart_failed"
                        logging.error(f"Failed to restart MPV process {process_id}")
                except Exception as e:
                    health_report["failed"] += 1
                    health_report["processes"][process_id] = f"error: {str(e)}"
                    logging.error(f"Error restarting MPV process {process_id}: {e}")

            # Check if controller is connected
            elif controller and not controller.connected:
                # Try to reconnect
                logging.warning(f"MPV controller {process_id} disconnected, attempting reconnect...")
                try:
                    connected = await controller.connect()
                    if connected:
                        health_report["healthy"] += 1
                        health_report["processes"][process_id] = "reconnected"
                        logging.info(f"Reconnected to MPV process {process_id}")
                    else:
                        # Reconnect failed, restart the process
                        logging.warning(f"Reconnect failed for process {process_id}, restarting...")
                        success = await self._restart_process(process_id)
                        if success:
                            health_report["restarted"] += 1
                            health_report["processes"][process_id] = "restarted_after_reconnect_fail"
                        else:
                            health_report["failed"] += 1
                            health_report["processes"][process_id] = "restart_failed_after_reconnect_fail"
                except Exception as e:
                    health_report["failed"] += 1
                    health_report["processes"][process_id] = f"reconnect_error: {str(e)}"
                    logging.error(f"Error reconnecting to MPV process {process_id}: {e}")

            else:
                # Process is healthy
                health_report["healthy"] += 1
                health_report["processes"][process_id] = "healthy"

        # Log summary
        if health_report["restarted"] > 0 or health_report["failed"] > 0:
            logging.info(f"{self.pool_name} Pool Health Check: {health_report['healthy']} healthy, "
                        f"{health_report['restarted']} restarted, {health_report['failed']} failed")

        return health_report


class AudioMPVPool(MPVProcessPool):
    """MPV pool specialized for audio streaming"""

    def __init__(self, pool_size: int = 2, socket_dir: str = SOCKET_DIR):
        super().__init__(pool_name="audio-mpv", pool_size=pool_size, socket_dir=socket_dir)

    def _get_mpv_command(self, socket_path: str) -> list:
        """Get mpv command configured for audio-only playback"""
        return [
            "mpv",
            "--vo=null",  # No video output - audio only
            f"--audio-device={AUDIO_DEVICE}",
            "--quiet",
            "--no-input-default-bindings",
            "--no-osc",
            f"--input-ipc-server={socket_path}",
            "--idle=yes",
            "--no-terminal",
            "--really-quiet"
        ]


class VideoMPVPool(MPVProcessPool):
    """MPV pool specialized for video playback with DRM/KMS"""

    def __init__(self, pool_size: int = 1, socket_dir: str = SOCKET_DIR):
        super().__init__(pool_name="video-mpv", pool_size=pool_size, socket_dir=socket_dir)

    def _get_mpv_command(self, socket_path: str) -> list:
        """Get mpv command configured for video playback with DRM"""
        return [
            "mpv",
            "--vo=drm",  # DRM video output
            "--drm-device=/dev/dri/card0",
            "--drm-connector=HDMI-A-1",
            f"--audio-device={AUDIO_DEVICE}",
            "--hwdec=v4l2m2m",  # Hardware decoding
            "--quiet",
            "--no-input-default-bindings",
            "--no-osc",
            f"--input-ipc-server={socket_path}",
            "--idle=yes",
            "--no-terminal",
            "--really-quiet"
        ]
