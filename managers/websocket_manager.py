"""
WebSocket Manager

Manages WebSocket connections and broadcasts real-time events to connected clients.
Used for Spotify now-playing updates and other real-time UI synchronization.
"""
import logging
import json
from typing import Set, Dict, Any
from fastapi import WebSocket


class WebSocketManager:
    """Manages WebSocket connections and event broadcasting"""

    def __init__(self):
        self.active_connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket, initial_data: dict = None):
        """Accept and register a new WebSocket connection

        Args:
            websocket: The WebSocket connection to register
            initial_data: Optional dict of initial state to send immediately after connection
        """
        await websocket.accept()
        self.active_connections.add(websocket)
        logging.info(f"WebSocket connected. Total connections: {len(self.active_connections)}")

        # Send initial state if provided
        if initial_data:
            try:
                await websocket.send_text(json.dumps(initial_data))
                logging.debug(f"Sent initial state to new WebSocket client")
            except Exception as e:
                logging.warning(f"Failed to send initial state: {e}")

    async def disconnect(self, websocket: WebSocket):
        """Unregister a WebSocket connection"""
        self.active_connections.discard(websocket)
        logging.info(f"WebSocket disconnected. Total connections: {len(self.active_connections)}")

    async def broadcast(self, event_type: str, data: Dict[str, Any]):
        """Broadcast an event to all connected WebSocket clients"""
        if not self.active_connections:
            logging.debug(f"No active WebSocket connections to broadcast {event_type}")
            return

        message = json.dumps({
            "event": event_type,
            "data": data
        })

        # Send to all connections, remove dead ones
        dead_connections = set()
        for websocket in self.active_connections:
            try:
                await websocket.send_text(message)
            except Exception as e:
                logging.warning(f"Failed to send to WebSocket client: {e}")
                dead_connections.add(websocket)

        # Clean up dead connections
        for websocket in dead_connections:
            self.active_connections.discard(websocket)

        if dead_connections:
            logging.info(f"Removed {len(dead_connections)} dead WebSocket connections")

        logging.debug(f"Broadcasted {event_type} to {len(self.active_connections)} clients")

    def get_connection_count(self) -> int:
        """Get the number of active WebSocket connections"""
        return len(self.active_connections)
