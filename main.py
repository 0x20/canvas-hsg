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

# Core components
from core.mpv_pools import AudioMPVPool, VideoMPVPool
from core.health_monitor import mpv_pool_health_monitor

# Managers
from managers.audio_manager import AudioManager
from managers.playback_manager import PlaybackManager
from managers.image_manager import ImageManager
from managers.stream_manager import StreamManager
from managers.screen_stream_manager import ScreenStreamManager

# System components
from managers.display_detector import DisplayCapabilityDetector
from managers.framebuffer_manager import FramebufferManager
from managers.hdmi_cec import HDMICECManager
from background_modes import BackgroundManager
from webcast_manager import WebcastManager

# API routes
from api.routes_audio import setup_audio_routes
from api.routes_playback import setup_playback_routes
from api.routes_streams import setup_stream_routes
from api.routes_screen import setup_screen_routes
from api.routes_display import setup_display_routes
from api.routes_background import setup_background_routes
from api.routes_cec import setup_cec_routes
from api.routes_system import setup_system_routes
from api.routes_webcast import setup_webcast_routes

# Config
from config import AUDIO_POOL_SIZE, VIDEO_POOL_SIZE

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Global manager instances (will be initialized in lifespan)
audio_pool: AudioMPVPool = None
video_pool: VideoMPVPool = None
audio_manager: AudioManager = None
playback_manager: PlaybackManager = None
image_manager: ImageManager = None
stream_manager: StreamManager = None
screen_stream_manager: ScreenStreamManager = None
background_manager: BackgroundManager = None
webcast_manager_instance: WebcastManager = None
display_detector = None
framebuffer_manager = None
cec_manager = None
health_task = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan management for FastAPI application.
    Handles startup and shutdown tasks.
    """
    global audio_pool, video_pool, audio_manager, playback_manager, image_manager
    global stream_manager, screen_stream_manager, background_manager
    global webcast_manager_instance, display_detector, framebuffer_manager, cec_manager
    global health_task

    # STARTUP
    logging.info("Starting HSG Canvas application...")

    try:
        # Initialize display detector
        logging.info("Initializing display detector...")
        display_detector = DisplayCapabilityDetector()
        await display_detector.initialize()

        # Initialize framebuffer
        logging.info("Initializing framebuffer...")
        framebuffer_manager = FramebufferManager()
        framebuffer_manager.initialize()

        # Initialize MPV pools
        logging.info(f"Initializing audio MPV pool (size={AUDIO_POOL_SIZE})...")
        audio_pool = AudioMPVPool(pool_size=AUDIO_POOL_SIZE)
        await audio_pool.initialize()

        logging.info(f"Initializing video MPV pool (size={VIDEO_POOL_SIZE})...")
        video_pool = VideoMPVPool(pool_size=VIDEO_POOL_SIZE)
        await video_pool.initialize()

        # Initialize background manager
        logging.info("Initializing background manager...")
        background_manager = BackgroundManager(display_detector, framebuffer_manager)

        # Initialize managers
        logging.info("Initializing managers...")
        audio_manager = AudioManager(audio_pool)
        playback_manager = PlaybackManager(video_pool, display_detector, background_manager)
        image_manager = ImageManager(display_detector)
        stream_manager = StreamManager()
        screen_stream_manager = ScreenStreamManager(display_detector)

        # Initialize CEC manager
        logging.info("Initializing HDMI-CEC manager...")
        cec_manager = HDMICECManager()

        # Initialize webcast manager
        logging.info("Initializing webcast manager...")
        webcast_manager_instance = WebcastManager()

        # Setup routers with managers
        logging.info("Setting up API routes...")
        app.include_router(setup_audio_routes(audio_manager))
        app.include_router(setup_playback_routes(playback_manager))
        app.include_router(setup_stream_routes(stream_manager))
        app.include_router(setup_screen_routes(screen_stream_manager))
        app.include_router(setup_display_routes(image_manager))
        app.include_router(setup_background_routes(background_manager))
        app.include_router(setup_cec_routes(cec_manager))
        app.include_router(setup_system_routes(audio_pool, video_pool, display_detector))
        app.include_router(setup_webcast_routes(webcast_manager_instance))

        # Start health monitor for MPV pools
        logging.info("Starting MPV pool health monitor...")
        health_task = asyncio.create_task(
            mpv_pool_health_monitor(audio_pool, video_pool)
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
        if health_task:
            health_task.cancel()
            try:
                await health_task
            except asyncio.CancelledError:
                pass

        # Stop background manager
        if background_manager:
            await background_manager.stop()

        # Stop webcast
        if webcast_manager_instance:
            await webcast_manager_instance.stop_webcast()

        # Cleanup managers
        if audio_manager:
            await audio_manager.stop_audio_stream()

        if playback_manager:
            await playback_manager.stop_playback()

        if stream_manager:
            await stream_manager.cleanup()

        if screen_stream_manager:
            await screen_stream_manager.stop_screen_stream()

        # Cleanup MPV pools
        if audio_pool:
            await audio_pool.cleanup()

        if video_pool:
            await video_pool.cleanup()

        # Cleanup framebuffer
        if framebuffer_manager:
            framebuffer_manager.cleanup()

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
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        log_level="info",
        reload=False  # Set to True for development
    )
