"""
WebSocket Manager

Manages WebSocket connections and broadcasts real-time events to connected clients.
Used for Spotify now-playing updates and other real-time UI synchronization.

Also exposes a tiny SSE-subscriber bus so the /canvas/events Server-Sent
Events endpoint can receive the same events as WebSocket clients without
opening a duplicate broadcast path.
"""
import asyncio
import logging
import json
from typing import Set, Dict, Any
from fastapi import WebSocket


class WebSocketManager:
    """Manages WebSocket connections and event broadcasting"""

    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
        # SSE subscribers: each one is an asyncio.Queue we push (event, data)
        # tuples to. broadcast() and broadcast_raw() fan out to these in
        # addition to the WebSocket clients.
        self._sse_subscribers: Set[asyncio.Queue] = set()

    def register_sse(self, queue: asyncio.Queue) -> None:
        self._sse_subscribers.add(queue)
        logging.info(f"SSE subscriber registered. Total: {len(self._sse_subscribers)}")

    def unregister_sse(self, queue: asyncio.Queue) -> None:
        self._sse_subscribers.discard(queue)
        logging.info(f"SSE subscriber removed. Total: {len(self._sse_subscribers)}")

    def _push_to_sse(self, event_type: str, data: Dict[str, Any]) -> None:
        """Best-effort push to all SSE queues. Drops if a queue is full —
        SSE consumers fall behind on slow renderers (e.g. the A20 BPi takes
        ~13 s per snapshot). The user picked 'coalesce — always show the
        latest' so dropping intermediate events is the right call."""
        for q in list(self._sse_subscribers):
            try:
                q.put_nowait((event_type, data))
            except asyncio.QueueFull:
                # Drop the oldest item, queue the new one
                try:
                    q.get_nowait()
                    q.put_nowait((event_type, data))
                except (asyncio.QueueEmpty, asyncio.QueueFull):
                    pass

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

    # A client that cannot take a message in this time is dropped, so one slow
    # remote screen does not hold up every display change.
    SEND_TIMEOUT = 2.0

    async def broadcast(self, event_type: str, data: Dict[str, Any]):
        """Broadcast an event to all connected WebSocket clients + SSE subscribers"""
        # Fan out to SSE consumers regardless of WS clients
        self._push_to_sse(event_type, data)
        await self._send_all(json.dumps({"event": event_type, "data": data}))

    async def broadcast_raw(self, data: Dict[str, Any]):
        """Broadcast a raw message (no event/data wrapping) to all connected clients"""
        await self._send_all(json.dumps(data))

    async def _send_all(self, message: str):
        """Send to every client in parallel; drop clients that fail or time out."""
        # Snapshot: clients may connect or disconnect while the sends wait.
        clients = list(self.active_connections)
        if not clients:
            return

        async def send(websocket: WebSocket) -> bool:
            try:
                await asyncio.wait_for(websocket.send_text(message), self.SEND_TIMEOUT)
                return True
            except Exception as e:
                logging.warning(f"Failed to send to WebSocket client: {e}")
                return False

        results = await asyncio.gather(*(send(ws) for ws in clients))
        dead = [ws for ws, ok in zip(clients, results) if not ok]
        for websocket in dead:
            self.active_connections.discard(websocket)
            try:
                await websocket.close()
            except Exception:
                pass
        if dead:
            logging.info(f"Removed {len(dead)} dead WebSocket connections")

    def get_connection_count(self) -> int:
        """Get the number of active WebSocket connections"""
        return len(self.active_connections)
