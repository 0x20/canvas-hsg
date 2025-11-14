"""
Cast Receiver Manager

Implements Chromecast receiver functionality so the Canvas can receive casts from phones/tablets.
Uses DIAL/SSDP for device discovery and simple receiver endpoints for media playback.
"""
import asyncio
import logging
import socket
import struct
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Optional, Dict, Any
from urllib.parse import urlparse

import netifaces

from config import PRODUCTION_PORT


class CastReceiverManager:
    """Manages Chromecast receiver functionality for incoming casts"""

    def __init__(self, playback_manager=None, audio_manager=None):
        """
        Initialize Cast Receiver Manager

        Args:
            playback_manager: PlaybackManager for video playback
            audio_manager: AudioManager for audio playback
        """
        self.playback_manager = playback_manager
        self.audio_manager = audio_manager

        # Receiver state
        self.device_name = "HSG Canvas"
        self.device_uuid = "hsg-canvas-receiver"
        self.is_running = False
        self.ssdp_task: Optional[asyncio.Task] = None

        # Current session
        self.current_session: Optional[Dict[str, Any]] = None
        self.session_id: Optional[str] = None

        # SSDP/DIAL configuration
        self.ssdp_port = 1900
        self.ssdp_addr = "239.255.255.250"
        self.dial_port = PRODUCTION_PORT  # Use same port as main FastAPI server

        # Get local IP
        self.local_ip = self._get_local_ip()

    def _get_local_ip(self) -> str:
        """Get the local IP address of the Pi"""
        try:
            # Try to get IP from common interface names on Pi
            for interface in ['eth0', 'wlan0', 'en0', 'wlan1']:
                try:
                    addrs = netifaces.ifaddresses(interface)
                    if netifaces.AF_INET in addrs:
                        ip = addrs[netifaces.AF_INET][0]['addr']
                        if ip and not ip.startswith('127.'):
                            logging.info(f"Found local IP {ip} on interface {interface}")
                            return ip
                except ValueError:
                    continue

            # Fallback: use socket method
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception as e:
            logging.error(f"Failed to get local IP: {e}")
            return "127.0.0.1"

    async def start_receiver(self) -> bool:
        """Start the cast receiver (SSDP discovery)"""
        try:
            if self.is_running:
                logging.info("Cast receiver already running")
                return True

            logging.info(f"Starting Cast receiver on {self.local_ip}...")

            # Start SSDP responder
            self.ssdp_task = asyncio.create_task(self._run_ssdp_responder())
            self.is_running = True

            logging.info(f"Cast receiver started - device discoverable as '{self.device_name}'")
            logging.info(f"Cast to: http://{self.local_ip}:{self.dial_port}/apps")
            return True

        except Exception as e:
            logging.error(f"Failed to start cast receiver: {e}")
            return False

    async def stop_receiver(self) -> bool:
        """Stop the cast receiver"""
        try:
            if not self.is_running:
                return True

            logging.info("Stopping Cast receiver...")

            # Stop SSDP responder
            if self.ssdp_task:
                self.ssdp_task.cancel()
                try:
                    await self.ssdp_task
                except asyncio.CancelledError:
                    pass
                self.ssdp_task = None

            # Stop current session
            if self.current_session:
                await self.stop_session()

            self.is_running = False
            logging.info("Cast receiver stopped")
            return True

        except Exception as e:
            logging.error(f"Failed to stop cast receiver: {e}")
            return False

    async def _run_ssdp_responder(self):
        """Run SSDP responder to make device discoverable using threading"""
        import threading

        def ssdp_thread():
            """Thread to handle SSDP requests"""
            try:
                # Create UDP socket for SSDP
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

                # Join multicast group
                mreq = struct.pack("4sl", socket.inet_aton(self.ssdp_addr), socket.INADDR_ANY)
                sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)

                # Bind to SSDP port
                sock.bind(('', self.ssdp_port))
                sock.settimeout(1.0)  # 1 second timeout to check is_running periodically

                logging.info(f"SSDP responder listening on {self.ssdp_addr}:{self.ssdp_port}")

                while self.is_running:
                    try:
                        # Receive SSDP M-SEARCH requests
                        data, addr = sock.recvfrom(1024)
                        message = data.decode('utf-8', errors='ignore')

                        # Check if it's an M-SEARCH for DIAL or Chromecast
                        if 'M-SEARCH' in message and ('dial-multiscreen' in message.lower() or
                                                       'cast' in message.lower()):
                            logging.info(f"Received SSDP M-SEARCH from {addr}")

                            # Send SSDP response
                            response = self._build_ssdp_response()
                            sock.sendto(response.encode('utf-8'), addr)
                            logging.info(f"Sent SSDP response to {addr}")

                    except socket.timeout:
                        # Normal - just checking if we should continue
                        continue
                    except Exception as e:
                        if self.is_running:  # Only log if not shutting down
                            logging.warning(f"SSDP error ({type(e).__name__}): {e}")

                sock.close()
                logging.info("SSDP thread stopped")

            except Exception as e:
                logging.error(f"SSDP responder error: {e}")

        try:
            # Start SSDP in a daemon thread
            thread = threading.Thread(target=ssdp_thread, daemon=True, name="SSDP-Responder")
            thread.start()

            # Keep the coroutine alive while the thread runs
            while self.is_running:
                await asyncio.sleep(1)

            # Wait for thread to finish
            thread.join(timeout=2)

        except Exception as e:
            logging.error(f"SSDP responder setup error: {e}")

    def _build_ssdp_response(self) -> str:
        """Build SSDP response message"""
        return (
            "HTTP/1.1 200 OK\r\n"
            f"LOCATION: http://{self.local_ip}:{self.dial_port}/dd.xml\r\n"
            "CACHE-CONTROL: max-age=1800\r\n"
            "EXT:\r\n"
            "BOOTID.UPNP.ORG: 1\r\n"
            "SERVER: Linux/3.14.0 UPnP/1.0 quick_ssdp/1.0\r\n"
            "ST: urn:dial-multiscreen-org:service:dial:1\r\n"
            f"USN: uuid:{self.device_uuid}::urn:dial-multiscreen-org:service:dial:1\r\n"
            "\r\n"
        )

    def get_device_description_xml(self) -> str:
        """Get DIAL device description XML"""
        return f"""<?xml version="1.0"?>
<root xmlns="urn:schemas-upnp-org:device-1-0">
  <specVersion>
    <major>1</major>
    <minor>0</minor>
  </specVersion>
  <device>
    <deviceType>urn:dial-multiscreen-org:device:dial:1</deviceType>
    <friendlyName>{self.device_name}</friendlyName>
    <manufacturer>Hackerspace Gent</manufacturer>
    <modelName>HSG Canvas</modelName>
    <UDN>uuid:{self.device_uuid}</UDN>
    <serviceList>
      <service>
        <serviceType>urn:dial-multiscreen-org:service:dial:1</serviceType>
        <serviceId>urn:dial-multiscreen-org:serviceId:dial</serviceId>
        <controlURL>/ssdp/notfound</controlURL>
        <eventSubURL>/ssdp/notfound</eventSubURL>
        <SCPDURL>/ssdp/notfound</SCPDURL>
      </service>
    </serviceList>
  </device>
</root>"""

    async def receive_cast(self, media_url: str, content_type: Optional[str] = None,
                          title: Optional[str] = None, metadata: Optional[Dict] = None) -> bool:
        """
        Receive and play a cast from a phone/tablet

        Args:
            media_url: URL of media to play
            content_type: MIME type of content
            title: Display title
            metadata: Additional metadata

        Returns:
            True if successful
        """
        try:
            # Stop any existing session
            if self.current_session:
                await self.stop_session()

            # Detect media type
            media_type = self._detect_media_type(media_url, content_type)

            logging.info(f"Receiving cast: {media_url} (type: {media_type})")

            # Create session
            self.session_id = f"session-{datetime.now().timestamp()}"
            self.current_session = {
                "media_url": media_url,
                "media_type": media_type,
                "content_type": content_type,
                "title": title or "Cast Media",
                "metadata": metadata or {},
                "started_at": datetime.now().isoformat(),
                "session_id": self.session_id
            }

            # Play based on media type
            success = False
            if media_type == "video":
                if self.playback_manager:
                    # Check if it's a YouTube URL
                    if 'youtube.com' in media_url or 'youtu.be' in media_url:
                        success = await self.playback_manager.play_youtube(media_url, mute=False)
                    else:
                        # For other video URLs, we'd need to add support in playback_manager
                        logging.warning(f"Non-YouTube video casting not yet supported: {media_url}")
                        # TODO: Add generic video URL support to playback_manager
                        success = False
            else:  # audio
                if self.audio_manager:
                    success = await self.audio_manager.start_audio_stream(media_url)

            if success:
                logging.info(f"Cast session started successfully: {self.session_id}")
                return True
            else:
                logging.error(f"Failed to start cast playback for: {media_url}")
                self.current_session = None
                self.session_id = None
                return False

        except Exception as e:
            logging.error(f"Failed to receive cast: {e}")
            self.current_session = None
            self.session_id = None
            return False

    async def stop_session(self) -> bool:
        """Stop the current cast session"""
        try:
            if not self.current_session:
                return True

            media_type = self.current_session.get("media_type")

            if media_type == "video" and self.playback_manager:
                await self.playback_manager.stop_playback()
            elif media_type == "audio" and self.audio_manager:
                await self.audio_manager.stop_audio_stream()

            logging.info(f"Cast session stopped: {self.session_id}")
            self.current_session = None
            self.session_id = None
            return True

        except Exception as e:
            logging.error(f"Failed to stop cast session: {e}")
            return False

    def _detect_media_type(self, media_url: str, content_type: Optional[str] = None) -> str:
        """Detect if media is audio or video"""
        # Check content type first
        if content_type:
            if 'video' in content_type.lower():
                return 'video'
            if 'audio' in content_type.lower():
                return 'audio'

        # Parse URL
        parsed = urlparse(media_url.lower())
        path = parsed.path

        # Check for video services
        if 'youtube.com' in parsed.netloc or 'youtu.be' in parsed.netloc:
            return 'video'
        if 'vimeo.com' in parsed.netloc:
            return 'video'

        # Check file extensions
        audio_extensions = ['.mp3', '.m4a', '.aac', '.ogg', '.opus', '.flac', '.wav']
        video_extensions = ['.mp4', '.mkv', '.webm', '.avi', '.mov', '.m4v']

        for ext in audio_extensions:
            if path.endswith(ext):
                return 'audio'

        for ext in video_extensions:
            if path.endswith(ext):
                return 'video'

        # Check for streaming patterns
        if any(pattern in media_url.lower() for pattern in ['.pls', '.m3u', 'radio', 'stream']):
            return 'audio'

        # Default to video for unknown types
        return 'video'

    def get_receiver_status(self) -> Dict[str, Any]:
        """Get current receiver status"""
        status = {
            "is_running": self.is_running,
            "device_name": self.device_name,
            "local_ip": self.local_ip,
            "dial_port": self.dial_port,
            "has_session": self.current_session is not None
        }

        if self.current_session:
            status["session"] = {
                "session_id": self.session_id,
                "media_url": self.current_session.get("media_url"),
                "media_type": self.current_session.get("media_type"),
                "title": self.current_session.get("title"),
                "started_at": self.current_session.get("started_at")
            }

        return status

    async def cleanup(self):
        """Cleanup receiver resources"""
        await self.stop_receiver()
        logging.info("Cast receiver manager cleaned up")
