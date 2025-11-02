"""
MPV IPC Controller

Handles IPC communication with a single mpv process via Unix socket.
"""
import asyncio
import json
import logging
import socket
import select
import errno
import time
from typing import Optional


class MPVController:
    """Handles IPC communication with a single mpv process"""

    def __init__(self, socket_path: str, process_id: int):
        self.socket_path = socket_path
        self.process_id = process_id
        self.socket: Optional[socket.socket] = None
        self.connected = False
        self.request_id = 0
        self.pending_requests = {}
        self.observed_properties = {}
        self.in_use = False

    async def connect(self, timeout: float = 5.0) -> bool:
        """Connect to mpv IPC socket"""
        try:
            self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.socket.settimeout(timeout)

            # Use asyncio to avoid blocking the event loop
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self.socket.connect, self.socket_path)

            self.socket.setblocking(False)
            self.connected = True
            logging.info(f"Connected to mpv process {self.process_id} at {self.socket_path}")
            return True
        except Exception as e:
            logging.error(f"Failed to connect to mpv process {self.process_id}: {e}")
            self.connected = False
            return False

    def disconnect(self):
        """Disconnect from mpv IPC socket"""
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
        self.socket = None
        self.connected = False
        self.pending_requests.clear()

    async def send_command(self, command: list, **kwargs) -> dict:
        """Send a command to mpv and return response"""
        if not self.connected:
            return {"error": "not_connected"}

        self.request_id += 1
        request = {
            "command": command,
            "request_id": self.request_id
        }
        request.update(kwargs)

        try:
            message = json.dumps(request) + '\n'
            # Use asyncio to avoid blocking the event loop
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self.socket.send, message.encode('utf-8'))

            # Wait for response
            response = await self._read_response(self.request_id)
            return response

        except Exception as e:
            # Try to reconnect if socket is broken
            if "Broken pipe" in str(e) or "Connection reset" in str(e):
                logging.info(f"Socket broken, attempting to reconnect for command {command}")
                try:
                    self.disconnect()
                    if await self.connect():
                        # Retry the command once after reconnecting
                        message = json.dumps(request) + '\n'
                        loop = asyncio.get_event_loop()
                        await loop.run_in_executor(None, self.socket.send, message.encode('utf-8'))
                        response = await self._read_response(self.request_id)
                        logging.info(f"Command {command} succeeded after reconnection")
                        return response
                    else:
                        logging.error(f"Failed to reconnect for command {command}")
                        return {"error": "reconnection_failed"}
                except Exception as reconnect_error:
                    logging.error(f"Reconnection attempt failed for command {command}: {reconnect_error}")
                    return {"error": str(reconnect_error)}

            logging.error(f"Failed to send command {command}: {e}")
            return {"error": str(e)}

    async def _read_response(self, request_id: int, timeout: float = 5.0) -> dict:
        """Read response from mpv socket"""
        start_time = time.time()
        buffer = ""
        loop = asyncio.get_event_loop()

        while time.time() - start_time < timeout:
            try:
                # Use run_in_executor for blocking select call
                ready, _, _ = await loop.run_in_executor(None, select.select, [self.socket], [], [], 0.1)
                if ready:
                    # Use run_in_executor for blocking recv call
                    data = await loop.run_in_executor(None, self.socket.recv, 4096)
                    if not data:
                        break
                    buffer += data.decode('utf-8')

                    # Process complete JSON lines
                    while '\n' in buffer:
                        line, buffer = buffer.split('\n', 1)
                        if line.strip():
                            try:
                                response = json.loads(line)
                                if response.get('request_id') == request_id:
                                    return response
                                elif 'event' in response:
                                    # Handle property change events
                                    self._handle_property_event(response)
                            except json.JSONDecodeError:
                                continue
            except socket.error as e:
                if e.errno == errno.EAGAIN or e.errno == errno.EWOULDBLOCK:
                    await asyncio.sleep(0.01)
                else:
                    break

        return {"error": "timeout"}

    def _handle_property_event(self, event: dict):
        """Handle property change events from mpv"""
        if event.get('event') == 'property-change':
            prop_name = event.get('name')
            prop_value = event.get('data')
            if prop_name in self.observed_properties:
                self.observed_properties[prop_name] = prop_value

    async def set_property(self, property_name: str, value) -> dict:
        """Set a property value"""
        return await self.send_command(["set_property", property_name, value])

    async def get_property(self, property_name: str) -> dict:
        """Get a property value"""
        return await self.send_command(["get_property", property_name])

    async def add_property(self, property_name: str, value: float) -> dict:
        """Add to a numeric property"""
        return await self.send_command(["add", property_name, value])

    async def multiply_property(self, property_name: str, value: float) -> dict:
        """Multiply a numeric property"""
        return await self.send_command(["multiply", property_name, value])

    async def cycle_property(self, property_name: str, direction: str = "up") -> dict:
        """Cycle through property values"""
        return await self.send_command(["cycle", property_name, direction])

    async def observe_property(self, property_name: str) -> dict:
        """Start observing a property for changes"""
        obs_id = len(self.observed_properties) + 1
        result = await self.send_command(["observe_property", obs_id, property_name])
        if result.get('error') == 'success':
            self.observed_properties[property_name] = None
        return result

    async def loadfile(self, filename: str, mode: str = "replace") -> dict:
        """Load a file for playback"""
        return await self.send_command(["loadfile", filename, mode])

    async def pause(self, state: bool = None) -> dict:
        """Pause/unpause playback"""
        if state is None:
            return await self.cycle_property("pause")
        else:
            return await self.set_property("pause", state)

    async def seek(self, position, mode: str = "relative") -> dict:
        """Seek to position"""
        return await self.send_command(["seek", position, mode])

    async def quit(self) -> dict:
        """Quit mpv"""
        return await self.send_command(["quit"])
