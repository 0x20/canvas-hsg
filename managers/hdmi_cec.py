"""
HDMI-CEC Manager

Manages HDMI-CEC functionality for TV/monitor power control.
"""
import os
import logging
import subprocess
from typing import Tuple, List, Dict


class HDMICECManager:
    """Manages HDMI-CEC functionality for TV/monitor power control"""

    def __init__(self):
        self.is_available = False
        self.cec_devices = []
        self.tv_address = "0"  # Default TV address
        self.cec_adapter = None
        self.command_timeout = 10  # seconds

        # Check CEC availability
        self._detect_cec_support()

    def _detect_cec_support(self) -> None:
        """Detect HDMI-CEC support and available devices"""
        try:
            # Check for CEC device files
            cec_devices = ["/dev/cec0", "/dev/cec1"]
            available_devices = []

            for device in cec_devices:
                if os.path.exists(device):
                    try:
                        # Test read access
                        with open(device, 'r'):
                            available_devices.append(device)
                    except PermissionError:
                        logging.warning(f"CEC device {device} exists but no permission")
                    except Exception:
                        pass  # Device exists but not accessible

            # Check for cec-client availability
            try:
                result = subprocess.run(["which", "cec-client"],
                                      capture_output=True, text=True, timeout=5)
                cec_client_available = result.returncode == 0
            except Exception:
                cec_client_available = False

            if available_devices and cec_client_available:
                self.is_available = True
                self.cec_adapter = available_devices[0]  # Use first available
                logging.info(f"HDMI-CEC available: adapter={self.cec_adapter}")

                # Skip initial scan to avoid blocking startup - scan will happen on first API call
            else:
                reasons = []
                if not available_devices:
                    reasons.append("no CEC devices found")
                if not cec_client_available:
                    reasons.append("cec-client not installed")
                logging.warning(f"HDMI-CEC not available: {', '.join(reasons)}")

        except Exception as e:
            logging.error(f"Error detecting CEC support: {e}")

    def _scan_cec_devices(self) -> None:
        """Scan for connected CEC devices"""
        try:
            cmd = ["cec-client", "-s", "-d", "1"]
            process = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                     text=True)

            stdout, stderr = process.communicate(input="scan\nq\n", timeout=self.command_timeout)

            if process.returncode == 0:
                # Parse scan results to find connected devices
                devices = []
                for line in stdout.split('\n'):
                    if 'device #' in line.lower() and 'tv' in line.lower():
                        # Found TV device, extract address
                        if '(' in line and ')' in line:
                            addr_part = line[line.find('(') + 1:line.find(')')]
                            if addr_part:
                                self.tv_address = addr_part.split('.')[0]  # Get first part
                        devices.append(line.strip())

                self.cec_devices = devices
                logging.info(f"CEC scan found {len(devices)} devices, TV address: {self.tv_address}")
            else:
                logging.warning(f"CEC scan failed: {stderr}")

        except subprocess.TimeoutExpired:
            logging.error("CEC scan timed out")
        except Exception as e:
            logging.error(f"Error scanning CEC devices: {e}")

    def _execute_cec_command(self, command: str) -> Tuple[bool, str]:
        """Execute a CEC command with timeout and error handling"""
        if not self.is_available:
            return False, "HDMI-CEC not available"

        try:
            cmd = ["cec-client", "-s", "-d", "1"]
            process = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                     text=True)

            input_cmd = f"{command}\nq\n"
            stdout, stderr = process.communicate(input=input_cmd, timeout=self.command_timeout)

            success = process.returncode == 0
            output = stdout if success else stderr

            return success, output.strip()

        except subprocess.TimeoutExpired:
            return False, "Command timed out"
        except Exception as e:
            return False, f"Command failed: {str(e)}"

    async def power_on_tv(self) -> Dict:
        """Turn on the TV via HDMI-CEC"""
        success, output = self._execute_cec_command(f"on {self.tv_address}")

        return {
            "success": success,
            "message": "TV power on command sent" if success else f"Failed to power on TV: {output}",
            "output": output,
            "tv_address": self.tv_address
        }

    async def power_off_tv(self) -> Dict:
        """Put TV in standby via HDMI-CEC"""
        success, output = self._execute_cec_command(f"standby {self.tv_address}")

        return {
            "success": success,
            "message": "TV standby command sent" if success else f"Failed to put TV in standby: {output}",
            "output": output,
            "tv_address": self.tv_address
        }

    async def get_tv_power_status(self) -> Dict:
        """Check TV power status via HDMI-CEC"""
        success, output = self._execute_cec_command(f"pow {self.tv_address}")

        # Parse power status from output
        power_status = "unknown"
        if success and output:
            if "on" in output.lower():
                power_status = "on"
            elif "standby" in output.lower() or "off" in output.lower():
                power_status = "standby"

        return {
            "success": success,
            "power_status": power_status,
            "output": output,
            "tv_address": self.tv_address
        }

    async def scan_devices(self) -> Dict:
        """Scan for CEC devices and return results"""
        self._scan_cec_devices()

        return {
            "success": self.is_available,
            "devices": self.cec_devices,
            "tv_address": self.tv_address,
            "adapter": self.cec_adapter
        }

    def get_status(self) -> Dict:
        """Get comprehensive CEC status information"""
        return {
            "available": self.is_available,
            "adapter": self.cec_adapter,
            "tv_address": self.tv_address,
            "devices_found": len(self.cec_devices),
            "devices": self.cec_devices,
            "command_timeout": self.command_timeout
        }
