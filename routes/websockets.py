"""WebSocket routes: now-playing events, display state and audio commands."""
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from utils.build import current_canvas_build


async def _serve(manager, websocket: WebSocket, initial_data, on_message=None):
    """Register a client, answer pings, pass JSON messages to on_message."""
    await manager.connect(websocket, initial_data)
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
            elif on_message:
                try:
                    msg = json.loads(data)
                except json.JSONDecodeError:
                    continue
                await on_message(msg)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logging.error(f"WebSocket error: {e}")
    finally:
        await manager.disconnect(websocket)


def display_state_payload(display_stack) -> dict:
    """The display_state data: the top item, the full stack and the build.

    The kiosk keeps a video mounted under silent overlays, so it needs the
    full stack. The build hash makes an old bundle reload itself.
    """
    payload = display_stack.current.to_dict()
    payload["stack"] = display_stack.get_stack()
    payload["app_build"] = current_canvas_build()
    return payload


def setup_websocket_routes(
    websocket_manager,
    now_playing,
    spotify_manager,
    display_ws_manager,
    display_stack,
    audio_ws_manager,
    audio_manager,
) -> APIRouter:
    router = APIRouter()

    @router.websocket("/ws/now-playing")
    @router.websocket("/ws/spotify-events")  # deprecated alias (carries all sources)
    async def now_playing_websocket(websocket: WebSocket):
        """Real-time now-playing track updates from any source (Spotify,
        Sendspin, Bluetooth, radio streams)."""
        await _serve(websocket_manager, websocket, now_playing.initial_event())

    @router.websocket("/ws/spotify-state")
    async def spotify_state_websocket(websocket: WebSocket):
        """Spotify playing/paused state changes"""
        initial_data = {
            "event": "spotify_state",
            "data": {"is_playing": bool(spotify_manager and spotify_manager.is_playing)},
        }
        await _serve(websocket_manager, websocket, initial_data)

    @router.websocket("/ws/display")
    async def display_websocket(websocket: WebSocket):
        """Display state: the current state on connect, then every change."""
        initial_data = {"event": "display_state", "data": display_state_payload(display_stack)}
        await _serve(display_ws_manager, websocket, initial_data)

    @router.post("/display/reload-clients")
    async def reload_display_clients():
        """Tell every connected canvas to reload its page. Used to push a fresh
        bundle to input-less kiosks without touching them.

        Distinct from POST /display/reload (CDP kiosk reload): this reaches every
        connected screen (kiosk + remote mirrors) via the WebSocket reload event."""
        await display_ws_manager.broadcast("reload", {})
        return {"message": "Reload sent to display clients"}

    @router.websocket("/ws/audio")
    async def audio_websocket(websocket: WebSocket):
        """Audio commands (backend -> browser) and status (browser -> backend).

        Backend sends: audio_play, audio_stop, audio_volume, audio_pause
        Browser sends: audio_status (periodic state reports), audio_ended
        """
        async def on_message(msg: dict):
            if msg.get("type") == "audio_status":
                audio_manager.handle_browser_status(msg)
            elif msg.get("type") == "audio_ended":
                await audio_manager.handle_browser_ended(msg.get("src", ""))

        await _serve(audio_ws_manager, websocket, audio_manager.play_command(), on_message)

    @router.get("/ws/status")
    async def websocket_status():
        """Get WebSocket connection status"""
        return {
            "spotify_events": websocket_manager.get_connection_count(),
            "display": display_ws_manager.get_connection_count(),
            "audio": audio_ws_manager.get_connection_count(),
        }

    return router
