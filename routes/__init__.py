"""
API routes, one module per router.

Each setup_*_routes() function takes the managers it needs and returns an
APIRouter. main.py includes them during startup.
"""
from routes.audio import setup_audio_routes
from routes.bluetooth import setup_bluetooth_routes
from routes.cec import setup_cec_routes
from routes.chromecast import setup_chromecast_routes, setup_output_target_routes
from routes.display import setup_display_routes
from routes.homeassistant import setup_homeassistant_routes
from routes.kiosk import setup_kiosk_routes
from routes.playback import setup_playback_routes
from routes.sendspin import setup_sendspin_routes
from routes.settings import setup_settings_routes
from routes.system import setup_system_routes
from routes.websockets import display_state_payload, setup_websocket_routes

__all__ = [
    "display_state_payload",
    "setup_audio_routes",
    "setup_bluetooth_routes",
    "setup_cec_routes",
    "setup_chromecast_routes",
    "setup_display_routes",
    "setup_homeassistant_routes",
    "setup_kiosk_routes",
    "setup_output_target_routes",
    "setup_playback_routes",
    "setup_sendspin_routes",
    "setup_settings_routes",
    "setup_system_routes",
    "setup_websocket_routes",
]
