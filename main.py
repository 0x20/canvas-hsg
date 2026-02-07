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
from managers.mpv_pools import AudioMPVPool, VideoMPVPool
from managers.health_monitor import mpv_pool_health_monitor
from managers.audio_manager import AudioManager
from managers.playback_manager import PlaybackManager
from managers.image_manager import ImageManager
from managers.stream_manager import StreamManager
from managers.screen_stream_manager import ScreenStreamManager
from managers.display_detector import DisplayCapabilityDetector
from managers.framebuffer_manager import FramebufferManager
from managers.hdmi_cec import HDMICECManager
from managers.background_modes import BackgroundManager
from managers.webcast_manager import WebcastManager
from managers.chromecast_manager import ChromecastManager
from managers.cast_receiver_manager import CastReceiverManager
from managers.output_target_manager import OutputTargetManager
from managers.spotify_manager import SpotifyManager

# API routes
from routes import (
    setup_audio_routes,
    setup_playback_routes,
    setup_stream_routes,
    setup_screen_routes,
    setup_display_routes,
    setup_background_routes,
    setup_cec_routes,
    setup_system_routes,
    setup_webcast_routes,
    setup_chromecast_routes,
    setup_cast_receiver_routes,
    setup_output_target_routes
)

# Config
from config import AUDIO_POOL_SIZE, VIDEO_POOL_SIZE, DEFAULT_PORT, PRODUCTION_PORT

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

        # Initialize framebuffer
        logging.info("Initializing framebuffer...")
        app.state.framebuffer_manager = FramebufferManager()
        app.state.framebuffer_manager.initialize()

        # Initialize MPV pools
        logging.info(f"Initializing audio MPV pool (size={AUDIO_POOL_SIZE})...")
        app.state.audio_pool = AudioMPVPool(pool_size=AUDIO_POOL_SIZE)
        await app.state.audio_pool.initialize()

        logging.info(f"Initializing video MPV pool (size={VIDEO_POOL_SIZE})...")
        app.state.video_pool = VideoMPVPool(pool_size=VIDEO_POOL_SIZE)
        await app.state.video_pool.initialize()

        # Initialize background manager with video pool
        logging.info("Initializing background manager...")
        app.state.background_manager = BackgroundManager(
            app.state.display_detector, app.state.framebuffer_manager, app.state.video_pool
        )

        # Start default background display
        logging.info("Starting default background display...")
        await app.state.background_manager.start_static_mode()

        # Initialize managers
        logging.info("Initializing managers...")
        app.state.audio_manager = AudioManager(app.state.audio_pool)

        # Initialize Spotify manager with audio manager integration
        logging.info("Initializing Spotify manager...")
        app.state.spotify_manager = SpotifyManager(app.state.audio_manager, app.state.background_manager)
        await app.state.spotify_manager.initialize()

        app.state.playback_manager = PlaybackManager(
            app.state.video_pool, app.state.display_detector,
            app.state.background_manager, app.state.audio_manager
        )
        app.state.image_manager = ImageManager(
            app.state.display_detector, app.state.framebuffer_manager, app.state.video_pool
        )
        app.state.stream_manager = StreamManager()
        app.state.screen_stream_manager = ScreenStreamManager(app.state.display_detector)

        # Initialize CEC manager
        logging.info("Initializing HDMI-CEC manager...")
        app.state.cec_manager = HDMICECManager()

        # Initialize webcast manager
        logging.info("Initializing webcast manager...")
        app.state.webcast_manager = WebcastManager()

        # Initialize chromecast manager
        logging.info("Initializing Chromecast manager...")
        app.state.chromecast_manager = ChromecastManager(
            app.state.audio_manager, app.state.playback_manager
        )

        # Initialize cast receiver manager (disabled - native phone apps require full Cast protocol)
        logging.info("Initializing Cast Receiver manager...")
        app.state.cast_receiver_manager = CastReceiverManager(
            app.state.playback_manager, app.state.audio_manager
        )

        # Initialize output target manager (unified target management)
        logging.info("Initializing Output Target manager...")
        app.state.output_target_manager = OutputTargetManager(
            app.state.audio_manager, app.state.playback_manager, app.state.chromecast_manager
        )

        # Chromecast discovery now uses subprocess isolation - ZERO file descriptor leaks
        logging.info("Discovering Chromecast devices...")
        await app.state.output_target_manager.discover_chromecast_targets()

        # Setup routers with managers
        logging.info("Setting up API routes...")
        app.include_router(setup_audio_routes(app.state.audio_manager, app.state.spotify_manager))
        app.include_router(setup_playback_routes(app.state.playback_manager))
        app.include_router(setup_stream_routes(app.state.stream_manager))
        app.include_router(setup_screen_routes(app.state.screen_stream_manager))
        app.include_router(setup_display_routes(app.state.image_manager, app.state.background_manager))
        app.include_router(setup_background_routes(app.state.background_manager))
        app.include_router(setup_cec_routes(app.state.cec_manager))
        app.include_router(setup_system_routes(app.state.audio_pool, app.state.video_pool, app.state.display_detector))
        app.include_router(setup_webcast_routes(app.state.webcast_manager))
        app.include_router(setup_chromecast_routes(app.state.chromecast_manager))
        app.include_router(setup_cast_receiver_routes(app.state.cast_receiver_manager))
        app.include_router(setup_output_target_routes(app.state.output_target_manager))

        # Start health monitor for MPV pools
        logging.info("Starting MPV pool health monitor...")
        app.state.health_task = asyncio.create_task(
            mpv_pool_health_monitor(app.state.audio_pool, app.state.video_pool)
        )

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
        # Stop health monitor
        if hasattr(app.state, 'health_task') and app.state.health_task:
            app.state.health_task.cancel()
            try:
                await app.state.health_task
            except asyncio.CancelledError:
                pass

        # Stop background manager
        if hasattr(app.state, 'background_manager') and app.state.background_manager:
            await app.state.background_manager.stop()

        # Stop webcast
        if hasattr(app.state, 'webcast_manager') and app.state.webcast_manager:
            await app.state.webcast_manager.stop_webcast()

        # Stop Chromecast
        if hasattr(app.state, 'chromecast_manager') and app.state.chromecast_manager:
            await app.state.chromecast_manager.cleanup()

        # Stop Cast Receiver
        if hasattr(app.state, 'cast_receiver_manager') and app.state.cast_receiver_manager:
            await app.state.cast_receiver_manager.cleanup()

        # Stop Output Target Manager
        if hasattr(app.state, 'output_target_manager') and app.state.output_target_manager:
            await app.state.output_target_manager.cleanup()

        # Cleanup managers
        if hasattr(app.state, 'audio_manager') and app.state.audio_manager:
            await app.state.audio_manager.stop_audio_stream()

        if hasattr(app.state, 'playback_manager') and app.state.playback_manager:
            await app.state.playback_manager.stop_playback()

        if hasattr(app.state, 'stream_manager') and app.state.stream_manager:
            await app.state.stream_manager.cleanup()

        if hasattr(app.state, 'screen_stream_manager') and app.state.screen_stream_manager:
            await app.state.screen_stream_manager.stop_screen_stream()

        # Cleanup MPV pools
        if hasattr(app.state, 'audio_pool') and app.state.audio_pool:
            await app.state.audio_pool.cleanup()

        if hasattr(app.state, 'video_pool') and app.state.video_pool:
            await app.state.video_pool.cleanup()

        # Cleanup framebuffer
        if hasattr(app.state, 'framebuffer_manager') and app.state.framebuffer_manager:
            app.state.framebuffer_manager.cleanup()

        logging.info("HSG Canvas application shut down successfully!")

    except Exception as e:
        logging.error(f"Error during shutdown: {e}")


# Create FastAPI app with lifespan
app = FastAPI(
    title="HSG Canvas",
    description="Media streaming and display management for Raspberry Pi",
    version="3.0.0-refactored",
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
