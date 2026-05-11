"""
HSG Canvas Main Application

This is the entry point for the HSG Canvas application.
It wires together all managers, pools, and API routes.
"""
import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

# Managers
from managers.display_stack import DisplayStack
from managers.audio_manager import AudioManager
from managers.playback_manager import PlaybackManager
from managers.image_manager import ImageManager
from managers.display_detector import DisplayCapabilityDetector
from managers.hdmi_cec import HDMICECManager
from managers.background_modes import BackgroundManager
from managers.webcast_manager import WebcastManager
from managers.chromecast_manager import ChromecastManager
from managers.output_target_manager import OutputTargetManager
from managers.spotify_manager import SpotifyManager
from managers.sendspin_manager import SendspinManager
from managers.bluetooth_manager import BluetoothManager
from managers.audio_conflict import AudioConflictManager
from managers.websocket_manager import WebSocketManager
from managers.chromium_manager import ChromiumManager
from managers.homeassistant_manager import HomeAssistantManager

# API routes
from routes import (
    setup_audio_routes,
    setup_playback_routes,
    setup_display_routes,
    setup_background_routes,
    setup_cec_routes,
    setup_system_routes,
    setup_webcast_routes,
    setup_chromecast_routes,
    setup_output_target_routes,
    setup_websocket_routes,
    setup_homeassistant_routes,
    setup_display_stack_routes,
    setup_sendspin_routes,
    setup_bluetooth_routes,
)

# Config
from config import DEFAULT_PORT, PRODUCTION_PORT

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan management for FastAPI application.
    Handles startup and shutdown tasks.
    All managers are stored on app.state instead of module globals.
    """
    # STARTUP
    logging.info("Starting HSG Canvas application...")

    try:
        # Initialize display detector
        logging.info("Initializing display detector...")
        app.state.display_detector = DisplayCapabilityDetector()
        await app.state.display_detector.initialize()

        # Initialize WebSocket managers (3 separate instances)
        logging.info("Initializing WebSocket managers...")
        app.state.websocket_manager = WebSocketManager()      # Spotify events
        app.state.display_ws_manager = WebSocketManager()      # Display state
        app.state.audio_ws_manager = WebSocketManager()        # Audio commands

        # Initialize display stack
        logging.info("Initializing display stack...")

        async def broadcast_display_state(item):
            """Callback: broadcast display state change to all connected clients"""
            await app.state.display_ws_manager.broadcast("display_state", item.to_dict())

        app.state.display_stack = DisplayStack(on_change=broadcast_display_state)

        # Initialize Chromium manager
        logging.info("Initializing Chromium manager...")
        app.state.chromium_manager = ChromiumManager(app.state.display_detector)

        # Initialize background manager with display stack
        logging.info("Initializing background manager...")
        app.state.background_manager = BackgroundManager(
            app.state.display_detector,
            app.state.display_stack
        )

        # Start Chromium once - it will stay running, React handles view switching
        logging.info("Starting Chromium with React app...")
        if app.state.chromium_manager:
            success = await app.state.chromium_manager.start_kiosk("http://127.0.0.1/canvas/")

            if success:
                app.state.background_manager.current_mode = "static_web"
                app.state.background_manager.is_running = True
                logging.info("Chromium started - React app managing display")
            else:
                logging.error("Failed to start Chromium kiosk mode")

        # Initialize managers
        logging.info("Initializing managers...")
        app.state.audio_manager = AudioManager(app.state.audio_ws_manager)

        # Initialize audio conflict manager (shared between Spotify and Sendspin)
        logging.info("Initializing audio conflict manager...")
        app.state.audio_conflict = AudioConflictManager()

        # Initialize Spotify manager
        logging.info("Initializing Spotify manager...")
        app.state.spotify_manager = SpotifyManager(
            app.state.audio_manager, app.state.background_manager, app.state.websocket_manager
        )
        app.state.spotify_manager.display_stack = app.state.display_stack
        app.state.spotify_manager.audio_conflict = app.state.audio_conflict
        await app.state.spotify_manager.initialize()

        # Initialize Sendspin manager
        logging.info("Initializing Sendspin manager...")
        app.state.sendspin_manager = SendspinManager(
            audio_manager=app.state.audio_manager,
            websocket_manager=app.state.websocket_manager,
            audio_conflict=app.state.audio_conflict,
        )
        app.state.sendspin_manager.display_stack = app.state.display_stack

        # Initialize Bluetooth manager
        logging.info("Initializing Bluetooth manager...")
        app.state.bluetooth_manager = BluetoothManager(
            audio_manager=app.state.audio_manager,
            websocket_manager=app.state.websocket_manager,
            audio_conflict=app.state.audio_conflict,
        )
        app.state.bluetooth_manager.display_stack = app.state.display_stack

        app.state.playback_manager = PlaybackManager(
            app.state.display_stack, app.state.display_detector,
            app.state.background_manager, app.state.audio_manager
        )

        # Wire cross-references between managers
        app.state.spotify_manager.playback_manager = app.state.playback_manager
        app.state.audio_manager.playback_manager = app.state.playback_manager
        app.state.audio_manager.spotify_manager = app.state.spotify_manager
        app.state.audio_manager.sendspin_manager = app.state.sendspin_manager
        app.state.sendspin_manager.playback_manager = app.state.playback_manager
        app.state.sendspin_manager.spotify_manager = app.state.spotify_manager
        app.state.sendspin_manager.bluetooth_manager = app.state.bluetooth_manager
        app.state.bluetooth_manager.playback_manager = app.state.playback_manager
        app.state.bluetooth_manager.spotify_manager = app.state.spotify_manager
        app.state.bluetooth_manager.sendspin_manager = app.state.sendspin_manager
        app.state.spotify_manager.bluetooth_manager = app.state.bluetooth_manager
        app.state.audio_manager.bluetooth_manager = app.state.bluetooth_manager

        # Start Sendspin listener (after all cross-refs are wired)
        await app.state.sendspin_manager.initialize()

        # Start Bluetooth polling (after all cross-refs are wired)
        await app.state.bluetooth_manager.initialize()

        app.state.image_manager = ImageManager(
            app.state.display_detector, app.state.display_stack
        )

        # Initialize CEC manager
        logging.info("Initializing HDMI-CEC manager...")
        app.state.cec_manager = HDMICECManager()

        # Initialize webcast manager
        logging.info("Initializing webcast manager...")
        app.state.webcast_manager = WebcastManager()

        # Initialize chromecast manager
        logging.info("Initializing Chromecast manager...")
        app.state.chromecast_manager = ChromecastManager(
            app.state.audio_manager, app.state.playback_manager, app.state.background_manager
        )

        # Initialize output target manager (unified target management)
        logging.info("Initializing Output Target manager...")
        app.state.output_target_manager = OutputTargetManager(
            app.state.audio_manager, app.state.playback_manager, app.state.chromecast_manager
        )

        # Chromecast discovery now uses subprocess isolation - ZERO file descriptor leaks
        logging.info("Discovering Chromecast devices...")
        await app.state.output_target_manager.discover_chromecast_targets()

        # Initialize Home Assistant manager
        logging.info("Initializing Home Assistant manager...")
        app.state.ha_manager = HomeAssistantManager(
            spotify_manager=app.state.spotify_manager,
            audio_manager=app.state.audio_manager,
            playback_manager=app.state.playback_manager,
            chromecast_manager=app.state.chromecast_manager,
            background_manager=app.state.background_manager,
            cec_manager=app.state.cec_manager,
            image_manager=app.state.image_manager,
            webcast_manager=app.state.webcast_manager,
            chromium_manager=app.state.chromium_manager,
            display_stack=app.state.display_stack,
        )
        await app.state.ha_manager.initialize()

        # Wire HA manager into SpotifyManager for instant state updates
        app.state.spotify_manager.ha_manager = app.state.ha_manager

        # Setup routers with managers
        logging.info("Setting up API routes...")
        app.include_router(setup_audio_routes(app.state.audio_manager, app.state.spotify_manager))
        app.include_router(setup_playback_routes(app.state.playback_manager))
        app.include_router(setup_display_routes(app.state.image_manager, app.state.background_manager))
        app.include_router(setup_background_routes(app.state.background_manager))
        app.include_router(setup_cec_routes(app.state.cec_manager))
        app.include_router(setup_system_routes(display_detector=app.state.display_detector))
        app.include_router(setup_webcast_routes(app.state.webcast_manager))
        app.include_router(setup_chromecast_routes(app.state.chromecast_manager))
        app.include_router(setup_output_target_routes(app.state.output_target_manager))

        # Setup Home Assistant routes
        app.include_router(setup_homeassistant_routes(app.state.ha_manager))

        # Setup Sendspin routes
        app.include_router(setup_sendspin_routes(app.state.sendspin_manager))

        # Setup Bluetooth routes
        app.include_router(setup_bluetooth_routes(app.state.bluetooth_manager))

        # Setup WebSocket routes (display + audio + spotify + sendspin + bluetooth)
        app.include_router(setup_websocket_routes(
            app.state.websocket_manager,
            app.state.spotify_manager,
            app.state.display_ws_manager,
            app.state.display_stack,
            app.state.audio_ws_manager,
            app.state.audio_manager,
            app.state.sendspin_manager,
            app.state.bluetooth_manager,
        ))

        # Setup display stack API routes
        app.include_router(setup_display_stack_routes(app.state.display_stack, app.state.chromium_manager))

        # Start periodic Chromium health check
        async def chromium_health_loop():
            await asyncio.sleep(30)  # Initial delay
            no_ws_count = 0
            while True:
                try:
                    if app.state.chromium_manager and app.state.chromium_manager.is_running():
                        await app.state.chromium_manager.check_health()

                        # Auto-reload if no display WebSocket connections for 2+ checks (60s)
                        display_ws = app.state.display_ws_manager
                        if display_ws and len(display_ws.active_connections) == 0:
                            no_ws_count += 1
                            if no_ws_count >= 2:
                                logging.warning("No display WebSocket connections for 60s — reloading Chromium page")
                                await app.state.chromium_manager.reload_page()
                                no_ws_count = 0
                        else:
                            no_ws_count = 0
                except Exception as e:
                    logging.error(f"Chromium health check error: {e}")
                await asyncio.sleep(30)

        app.state._chromium_health_task = asyncio.create_task(chromium_health_loop())

        logging.info("HSG Canvas application started successfully!")

    except Exception as e:
        logging.error(f"Failed to start HSG Canvas: {e}")
        import traceback
        logging.error(f"Traceback: {traceback.format_exc()}")
        raise

    yield  # Application is running

    # SHUTDOWN
    logging.info("Shutting down HSG Canvas application...")

    try:
        # Cancel health check task
        if hasattr(app.state, '_chromium_health_task'):
            app.state._chromium_health_task.cancel()

        # Stop Bluetooth manager
        if hasattr(app.state, 'bluetooth_manager') and app.state.bluetooth_manager:
            await app.state.bluetooth_manager.cleanup()

        # Stop Sendspin manager
        if hasattr(app.state, 'sendspin_manager') and app.state.sendspin_manager:
            await app.state.sendspin_manager.cleanup()

        # Restore any muted audio sources
        if hasattr(app.state, 'audio_conflict') and app.state.audio_conflict:
            await app.state.audio_conflict.unmute_all()

        # Stop Home Assistant manager
        if hasattr(app.state, 'ha_manager') and app.state.ha_manager:
            await app.state.ha_manager.cleanup()

        # Stop Chromium manager
        if hasattr(app.state, 'chromium_manager') and app.state.chromium_manager:
            await app.state.chromium_manager.stop()

        # Stop background manager
        if hasattr(app.state, 'background_manager') and app.state.background_manager:
            await app.state.background_manager.stop()

        # Stop webcast
        if hasattr(app.state, 'webcast_manager') and app.state.webcast_manager:
            await app.state.webcast_manager.stop_webcast()

        # Stop Chromecast
        if hasattr(app.state, 'chromecast_manager') and app.state.chromecast_manager:
            await app.state.chromecast_manager.cleanup()

        # Stop Output Target Manager
        if hasattr(app.state, 'output_target_manager') and app.state.output_target_manager:
            await app.state.output_target_manager.cleanup()

        # Cleanup audio manager
        if hasattr(app.state, 'audio_manager') and app.state.audio_manager:
            await app.state.audio_manager.stop_audio_stream()

        # Cleanup playback manager
        if hasattr(app.state, 'playback_manager') and app.state.playback_manager:
            await app.state.playback_manager.stop_playback()

        logging.info("HSG Canvas application shut down successfully!")

    except Exception as e:
        logging.error(f"Error during shutdown: {e}")


# Create FastAPI app with lifespan
app = FastAPI(
    title="HSG Canvas",
    description="Media streaming and display management for Raspberry Pi",
    version="4.0.0-all-react",
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

# Mount static files if directory exists
if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")


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
