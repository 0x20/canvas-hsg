"""
HSG Canvas Main Application

This is the entry point for the HSG Canvas application.
It wires together all managers and API routes.
"""
import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles

# Managers
from managers.display_stack import DisplayStack
from managers.audio_manager import AudioManager
from managers.station_art import StationArtCache
from managers.playback_manager import PlaybackManager
from managers.image_manager import ImageManager
from managers.display_detector import DisplayCapabilityDetector
from managers.hdmi_cec import HDMICECManager
from managers.background_modes import BackgroundManager
from managers.chromecast_manager import ChromecastManager
from managers.output_target_manager import OutputTargetManager
from managers.spotify_manager import SpotifyManager
from managers.sendspin_manager import SendspinManager
try:
    from managers.sendspin_artwork_client import SendspinArtworkClient
except Exception as _artwork_import_err:
    # aiosendspin missing or an API change must not take down the whole app —
    # only the album-art feature degrades.
    SendspinArtworkClient = None
    logging.warning(f"Sendspin artwork display client unavailable: {_artwork_import_err}")
from managers.bluetooth_manager import BluetoothManager
from managers.audio_conflict import AudioConflictManager
from managers.now_playing import NowPlaying
from managers.websocket_manager import WebSocketManager
from managers.chromium_manager import ChromiumManager
from managers.homeassistant_manager import HomeAssistantManager
from utils.proc import run

# API routes
from routes import (
    display_state_payload,
    setup_audio_routes,
    setup_playback_routes,
    setup_display_routes,
    setup_cec_routes,
    setup_system_routes,
    setup_chromecast_routes,
    setup_output_target_routes,
    setup_websocket_routes,
    setup_homeassistant_routes,
    setup_kiosk_routes,
    setup_sendspin_routes,
    setup_bluetooth_routes,
)

# Config
from config import DEFAULT_PORT, PRODUCTION_PORT, CANVAS_DOMAIN, DEVICE_NAME, DEVICE_MANUFACTURER, APP_VERSION, SENDSPIN_NAME, SENDSPIN_ART_STATE_DIR, STATION_ART_CACHE_DIR

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

HEALTH_CHECK_INTERVAL = 30


class SPAStaticFiles(StaticFiles):
    """StaticFiles that tells browsers to revalidate the SPA shell on every
    load. Vite fingerprints its assets (hashed filenames), so those stay
    cacheable forever, but index.html references the current hashes — if a
    browser serves a stale index.html it loads a dead bundle. Kiosks can't be
    hard-reloaded by hand, so we mark the HTML no-cache to guarantee a plain
    reload (or power-cycle) picks up a freshly built bundle."""

    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        # path is "." for the directory root (served as index.html via
        # html=True) or "index.html"/"*.html" for an explicit request.
        if path == "." or path.endswith(".html"):
            response.headers["Cache-Control"] = "no-cache"
        return response


async def _restart_raspotify(reason: str):
    logging.warning(f"Restarting raspotify: {reason}")
    await run("sudo", "systemctl", "restart", "raspotify", timeout=10)
    logging.info("Raspotify restarted")


async def _check_raspotify_health(spotify_manager):
    """Restart raspotify if it's stuck on fatal errors or has gone silent
    while the Spotify session is supposed to be active."""
    # ── 1. Fatal errors in the last 60 seconds ──
    _, recent_logs = await run("journalctl", "-u", "raspotify", "--since", "60 sec ago", "--no-pager", "-q")
    error_count = (
        recent_logs.count("429 Too Many Requests")
        + recent_logs.count("StatusCode(403)")
        + recent_logs.count("FailedPrecondition")
    )
    if error_count >= 3:
        await _restart_raspotify(f"{error_count} fatal errors in 60s")
        return

    # ── 2. Liveness: silent logs while Spotify thinks it's playing ──
    # If our SpotifyManager believes a session is connected but raspotify
    # has produced no log output in the last 10 minutes, it's a zombie.
    if spotify_manager.is_playing or spotify_manager.is_session_connected:
        rc, silent = await run("journalctl", "-u", "raspotify", "--since", "10 min ago", "--no-pager", "-q")
        if rc == 0 and not silent.strip():
            await _restart_raspotify("silent for 10 min while session active")


async def _check_kiosk_health(chromium_manager, display_ws_manager, state: dict):
    """Start the kiosk again after a crash; reload it when it shows the wrong page."""
    if not await chromium_manager.check_health():
        state["no_ws"] = 0
        return

    # Fast path: if the kiosk landed on an error page (e.g. 502 from Angie
    # during a restart race), the title won't contain "HSG Canvas". Reload
    # immediately instead of waiting for the 60s no-WS heuristic.
    title = await chromium_manager.get_page_title()
    if title is not None and "HSG Canvas" not in title:
        logging.warning(f"Kiosk on unexpected page (title={title!r}) — reloading")
        await chromium_manager.reload_page()
        state["no_ws"] = 0
        return

    # Reload if no display WebSocket connections for 2+ checks (60s)
    if display_ws_manager.get_connection_count() == 0:
        state["no_ws"] += 1
        if state["no_ws"] >= 2:
            logging.warning("No display WebSocket connections for 60s — reloading Chromium page")
            await chromium_manager.reload_page()
            state["no_ws"] = 0
    else:
        state["no_ws"] = 0


async def health_check_loop(app: FastAPI):
    await asyncio.sleep(HEALTH_CHECK_INTERVAL)  # Initial delay
    state = {"no_ws": 0}
    while True:
        for check in (
            lambda: _check_kiosk_health(app.state.chromium_manager, app.state.display_ws_manager, state),
            lambda: _check_raspotify_health(app.state.spotify_manager),
        ):
            try:
                await check()
            except Exception as e:
                logging.error(f"Health check error: {e}")
        await asyncio.sleep(HEALTH_CHECK_INTERVAL)


async def _discover_chromecasts(output_target_manager):
    """Chromecast discovery takes up to ~10 s: run it after startup."""
    try:
        await output_target_manager.discover_chromecast_targets()
    except Exception as e:
        logging.error(f"Chromecast discovery failed: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan management for FastAPI application.
    Handles startup and shutdown tasks.
    All managers are stored on app.state instead of module globals.
    """
    # STARTUP
    logging.info("Starting HSG Canvas application...")
    s = app.state

    try:
        s.display_detector = DisplayCapabilityDetector()
        await s.display_detector.initialize()

        # WebSocket managers (3 separate instances)
        s.websocket_manager = WebSocketManager()      # Now-playing events
        s.display_ws_manager = WebSocketManager()     # Display state
        s.audio_ws_manager = WebSocketManager()       # Audio commands

        async def on_display_change(_item):
            """Broadcast every stack change, and release the video's audio
            claim when no video is left on the stack."""
            await s.display_ws_manager.broadcast("display_state", display_state_payload(s.display_stack))
            await s.playback_manager.on_stack_change()

        s.display_stack = DisplayStack(on_change=on_display_change)
        # Audio: one coordinator decides which source is audible
        s.audio_conflict = AudioConflictManager()
        s.playback_manager = PlaybackManager(s.display_stack, s.audio_conflict)
        s.chromium_manager = ChromiumManager(s.display_detector)

        # Apply the persisted idle-screen settings (background art + logo/QR
        # flags + QR target) to the base layer so the kiosk renders them from
        # the first frame.
        s.background_manager = BackgroundManager(s.display_stack)
        await s.background_manager.apply_overlay_settings()

        s.audio_manager = AudioManager(s.audio_ws_manager, s.audio_conflict)
        # Station-logo cache: resolves and stores radio artwork on disk so the
        # canvas renders it from the Pi instead of a name on a blank backdrop.
        s.station_art = StationArtCache(STATION_ART_CACHE_DIR)
        s.audio_manager.station_art = s.station_art
        s.audio_manager.display_stack = s.display_stack
        # Same now-playing WS the card listens on — lets audio streams
        # (SomaFM etc.) drive it with live track metadata.
        s.audio_manager.now_playing_ws = s.websocket_manager

        s.spotify_manager = SpotifyManager(s.websocket_manager)
        s.sendspin_manager = SendspinManager(s.websocket_manager, s.audio_conflict)
        s.bluetooth_manager = BluetoothManager(s.websocket_manager, s.audio_conflict)
        for manager in (s.spotify_manager, s.sendspin_manager, s.bluetooth_manager):
            manager.display_stack = s.display_stack
        s.spotify_manager.audio_conflict = s.audio_conflict
        # Spotify stays silent while Bluetooth or Sendspin shows
        s.spotify_manager.bluetooth_manager = s.bluetooth_manager
        s.spotify_manager.sendspin_manager = s.sendspin_manager

        s.audio_conflict.audio_manager = s.audio_manager
        s.audio_conflict.playback_manager = s.playback_manager
        s.audio_conflict.spotify_manager = s.spotify_manager
        s.audio_conflict.sendspin_manager = s.sendspin_manager
        s.audio_conflict.bluetooth_manager = s.bluetooth_manager

        # Read only: the combined /audio/status report
        s.audio_manager.playback_manager = s.playback_manager
        s.audio_manager.spotify_manager = s.spotify_manager
        s.audio_manager.sendspin_manager = s.sendspin_manager
        s.audio_manager.bluetooth_manager = s.bluetooth_manager

        s.now_playing = NowPlaying(s.spotify_manager, s.sendspin_manager,
                                   s.bluetooth_manager, s.audio_manager)

        await s.spotify_manager.initialize()
        await s.sendspin_manager.initialize()

        # Sendspin ARTWORK display client — receives Music Assistant album art
        # as binary frames over the LAN and feeds it to the now-playing view.
        s.sendspin_artwork_client = None
        if SendspinArtworkClient is not None:
            logging.info("Starting Sendspin artwork display client...")
            s.sendspin_artwork_client = SendspinArtworkClient(
                state_dir=SENDSPIN_ART_STATE_DIR,
                # Friendly name MA shows for this display — labelled after the
                # speaker it accompanies so it's clearly the art companion, not
                # a second player to cast to (e.g. "Kenwood Speakers - art").
                client_name=f"{SENDSPIN_NAME} - art",
                # Device identity so MA doesn't log unknown/blank player details.
                product_name=DEVICE_NAME,
                manufacturer=DEVICE_MANUFACTURER,
                software_version=APP_VERSION,
                on_artwork=s.sendspin_manager.on_artwork_updated,
            )
            s.sendspin_manager.artwork_client = s.sendspin_artwork_client
            await s.sendspin_artwork_client.start()

        await s.bluetooth_manager.initialize()

        s.image_manager = ImageManager(s.display_stack)
        s.cec_manager = HDMICECManager()
        s.chromecast_manager = ChromecastManager(s.audio_manager, s.playback_manager)
        s.output_target_manager = OutputTargetManager(
            s.audio_manager, s.playback_manager, s.chromecast_manager
        )
        s.chromecast_discovery_task = asyncio.create_task(_discover_chromecasts(s.output_target_manager))

        s.ha_manager = HomeAssistantManager(
            spotify_manager=s.spotify_manager,
            audio_manager=s.audio_manager,
            playback_manager=s.playback_manager,
            chromecast_manager=s.chromecast_manager,
            background_manager=s.background_manager,
            cec_manager=s.cec_manager,
            image_manager=s.image_manager,
            chromium_manager=s.chromium_manager,
            display_stack=s.display_stack,
        )
        await s.ha_manager.initialize()
        # Instant state updates for HA
        s.spotify_manager.ha_manager = s.ha_manager

        logging.info("Setting up API routes...")
        for router in (
            setup_audio_routes(s.audio_manager, s.spotify_manager),
            setup_playback_routes(s.playback_manager),
            setup_display_routes(s.display_stack, s.image_manager, s.background_manager, s.chromium_manager),
            setup_cec_routes(s.cec_manager),
            setup_system_routes(display_detector=s.display_detector),
            setup_chromecast_routes(s.chromecast_manager),
            setup_output_target_routes(s.output_target_manager),
            setup_homeassistant_routes(s.ha_manager),
            setup_sendspin_routes(s.sendspin_manager),
            setup_bluetooth_routes(s.bluetooth_manager),
            setup_websocket_routes(
                s.websocket_manager, s.now_playing, s.spotify_manager,
                s.display_ws_manager, s.display_stack,
                s.audio_ws_manager, s.audio_manager,
            ),
            # Kiosk routes MUST be registered before the /canvas StaticFiles
            # mount below so /canvas/kiosk and /canvas/events match the
            # explicit handlers rather than being captured by the static mount.
            setup_kiosk_routes(s.websocket_manager, s.now_playing),
        ):
            app.include_router(router)

        # The Firefox kiosk loads `/canvas` WITHOUT a trailing slash. The
        # StaticFiles mount answers that with a 307 to `/canvas/`, which the
        # kiosk then serves from its own HTTP cache — so a rebuilt bundle never
        # reaches it (only `GET /canvas` ever hits the server each boot). Serve
        # index.html directly here with no-store: every boot fetches fresh HTML,
        # which references the current fingerprinted bundle, forcing the new JS
        # to download. Asset URLs are absolute (vite base=/canvas/), so serving
        # the shell at the slashless URL resolves them fine.
        if os.path.exists("frontend/dist/index.html"):
            @app.get("/canvas", include_in_schema=False)
            async def canvas_entry():
                return FileResponse(
                    "frontend/dist/index.html",
                    headers={"Cache-Control": "no-store"},
                )

        # Mount the built React canvas LAST. The mount catches anything
        # under /canvas/ that wasn't matched above (the SPA itself).
        if os.path.exists("frontend/dist"):
            app.mount("/canvas", SPAStaticFiles(directory="frontend/dist", html=True), name="canvas")

        # Launch Chromium in the background. During lifespan startup uvicorn
        # is not yet bound, so Angie's upstream is down and Chromium would land
        # on a 502 page. start_kiosk_when_ready polls /canvas/ until it returns
        # 2xx; the await yields, lifespan finishes, uvicorn binds, and the task
        # proceeds against a healthy upstream.
        #
        # Use the canvas mDNS domain rather than 127.0.0.1 so the YouTube
        # IFrame embed's `origin` parameter is a non-loopback hostname —
        # YouTube rejects loopback origins with Error 153 ("Video
        # unavailable"). CANVAS_DOMAIN is configurable per instance.
        # audio=1 marks this as THE audio-output display: only the Pi's own
        # kiosk plays sound and reports playback status. Other screens loading
        # /canvas are silent display-only mirrors.
        kiosk_url = f"http://{CANVAS_DOMAIN}/canvas/?keepalive=1&audio=1"
        s.kiosk_launch_task = asyncio.create_task(s.chromium_manager.start_kiosk_when_ready(kiosk_url))

        # Keeps the kiosk and Raspotify alive
        s.health_check_task = asyncio.create_task(health_check_loop(app))

        logging.info("HSG Canvas application started successfully!")

    except Exception:
        logging.exception("Failed to start HSG Canvas")
        raise

    yield  # Application is running

    # SHUTDOWN: every step runs, even when an earlier one fails. The display
    # stack is not cleared, so remote screens keep their view over a restart.
    logging.info("Shutting down HSG Canvas application...")

    async def cancel(task):
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass

    steps = [
        ("health check", lambda: cancel(s.health_check_task)),
        ("kiosk launch", lambda: cancel(s.kiosk_launch_task)),
        ("chromecast discovery", lambda: cancel(s.chromecast_discovery_task)),
        ("bluetooth", s.bluetooth_manager.cleanup),
        ("sendspin", s.sendspin_manager.cleanup),
        ("audio unmute", s.audio_conflict.unmute_all),
        ("home assistant", s.ha_manager.cleanup),
        ("chromium", s.chromium_manager.stop),
        ("chromecast", s.chromecast_manager.cleanup),
        ("output targets", s.output_target_manager.cleanup),
        ("audio", s.audio_manager.cleanup),
    ]
    if s.sendspin_artwork_client:
        steps.insert(3, ("sendspin artwork", s.sendspin_artwork_client.stop))
    for name, step in steps:
        try:
            await step()
        except Exception as e:
            logging.error(f"Shutdown step '{name}' failed: {e}")

    logging.info("HSG Canvas application shut down")


# Create FastAPI app with lifespan
app = FastAPI(
    title="HSG Canvas",
    description="Media streaming and display management for Raspberry Pi",
    version=APP_VERSION,
    lifespan=lifespan
)


@app.get("/", response_class=HTMLResponse)
async def web_interface():
    """Serve the web interface"""
    try:
        with open("index.html", "r") as f:
            return f.read()
    except FileNotFoundError:
        return """
        <h1>Error: index.html not found</h1>
        <p>Please create an index.html file in the same directory as the Python server.</p>
        <p>You can access the API documentation at <a href="/docs">/docs</a></p>
        """

# Mount /static at module-load (no kiosk-route conflict). The /canvas mount
# is deferred to lifespan so the kiosk routes can be registered first —
# Starlette matches routes in registration order.
if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")

# Cached station logos. Created up front so the mount exists even before the
# first stream fills the cache.
os.makedirs(STATION_ART_CACHE_DIR, exist_ok=True)
app.mount("/station-art", StaticFiles(directory=STATION_ART_CACHE_DIR), name="station-art")


if __name__ == "__main__":
    import argparse
    import uvicorn

    # Parse command line arguments
    parser = argparse.ArgumentParser(description='HSG Canvas - Media streaming server')
    parser.add_argument('--production', action='store_true',
                       help='Run in production mode (port 80)')
    parser.add_argument('--port', type=int, default=None,
                       help='Custom port (overrides --production)')
    args = parser.parse_args()

    # Determine port
    if args.port:
        port = args.port
    elif args.production:
        port = PRODUCTION_PORT
    else:
        port = DEFAULT_PORT

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        log_level="info",
        reload=False  # Set to True for development
    )
