"""Routes for tiny external kiosk panels (e.g. 320x240 BPi display).

GET /canvas/kiosk   — server-rendered HTML, current track baked in,
                      edge-to-edge 320x240, no JS, no live WebSocket.
                      Optimised for headless-chromium screenshotting.
GET /canvas/events  — Server-Sent Events stream. Emits one event per
                      track change. Outbound HTTP only, NAT/firewall
                      friendly. Auto-reconnects via SSE protocol.
"""
import asyncio
import html
import json

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, StreamingResponse


def setup_kiosk_routes(websocket_manager, now_playing) -> APIRouter:
    router = APIRouter()

    @router.get("/canvas/kiosk", response_class=HTMLResponse)
    async def kiosk_view():
        """320×240 server-rendered now-playing snapshot. No JS, no WS."""
        t = now_playing.kiosk_track()
        # Escape user-provided text for safe HTML embedding
        name = html.escape(t["name"]) or "—"
        artists = html.escape(t["artists"]) or ""
        album = html.escape(t["album"]) or ""
        art = html.escape(t["album_art_url"], quote=True)
        # If there's no album art, the <img> tag with empty src would 404 —
        # omit it entirely. Layout uses CSS grid so the text column expands.
        art_html = f'<img src="{art}" width="96" height="96" alt="">' if art else '<div class="art-placeholder"></div>'
        body = f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=320, initial-scale=1, user-scalable=no">
<title>HSG Canvas</title>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
html, body {{ width: 320px; height: 240px; background: #000; color: #fff;
              font-family: 'Inter', 'Helvetica', sans-serif; overflow: hidden; }}
.kiosk {{ display: grid; grid-template-columns: 96px 1fr; gap: 12px;
         padding: 12px; width: 320px; height: 240px; }}
.art img, .art-placeholder {{ width: 96px; height: 96px; background: #222;
                              display: block; image-rendering: pixelated; }}
.text {{ overflow: hidden; }}
.title {{ font-size: 22px; font-weight: 700; line-height: 1.1;
          overflow: hidden; text-overflow: ellipsis; display: -webkit-box;
          -webkit-line-clamp: 3; -webkit-box-orient: vertical; }}
.artist {{ font-size: 14px; color: #cfd8e3; margin-top: 6px;
           white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
.footer {{ position: absolute; left: 12px; bottom: 8px; right: 12px;
           font-size: 11px; color: #6a7280;
           white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
</style>
</head><body>
<div class="kiosk">
  <div class="art">{art_html}</div>
  <div class="text">
    <div class="title">{name}</div>
    <div class="artist">{artists}</div>
  </div>
  <div class="footer">{album}</div>
</div>
</body></html>"""
        # Disable any caching so the render is always fresh per fetch
        return HTMLResponse(content=body, headers={"Cache-Control": "no-store, no-cache, must-revalidate"})

    @router.get("/canvas/events")
    async def kiosk_events(request: Request):
        """SSE stream of track-change events.

        First event is the current state on connect, then one event per
        change. Auto-reconnect via the SSE `retry:` directive.
        """
        async def event_gen():
            queue: asyncio.Queue = asyncio.Queue(maxsize=4)
            websocket_manager.register_sse(queue)
            try:
                # Tell client to retry every 5 s on disconnect
                yield "retry: 5000\n\n"
                # Initial paint — current state
                initial = now_playing.kiosk_track()
                yield f"event: track\ndata: {json.dumps(initial)}\n\n"

                # Heartbeat every 30 s to keep proxies from killing the
                # connection. SSE comments (lines starting with ':') are
                # ignored by the client but reset idle timers.
                heartbeat = 30.0
                while True:
                    if await request.is_disconnected():
                        break
                    try:
                        event_type, data = await asyncio.wait_for(queue.get(), timeout=heartbeat)
                    except asyncio.TimeoutError:
                        yield ": ping\n\n"
                        continue
                    # Only forward the events the kiosk cares about
                    if event_type in ("track_changed", "playback_state", "playing", "paused"):
                        payload = now_playing.kiosk_track()
                        yield f"event: track\ndata: {json.dumps(payload)}\n\n"
            finally:
                websocket_manager.unregister_sse(queue)

        return StreamingResponse(
            event_gen(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-store",
                "X-Accel-Buffering": "no",  # disable proxy buffering
                "Connection": "keep-alive",
            },
        )

    return router
