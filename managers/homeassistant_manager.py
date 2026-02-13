"""
HomeAssistant Manager

Two-way integration with Home Assistant:
- HSG -> HA: Push canvas state as media_player entity via REST API
- HA -> HSG: Subscribe to HA entity state changes via WebSocket API and trigger local actions
"""
import asyncio
import logging
import os
import aiohttp
import json
import yaml
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List


CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "homeassistant.yaml")


class HomeAssistantManager:
    """Manages Home Assistant entity state and automation subscriptions"""

    def __init__(self, spotify_manager=None, audio_manager=None, playback_manager=None,
                 chromecast_manager=None, background_manager=None, cec_manager=None,
                 image_manager=None, webcast_manager=None, chromium_manager=None):
        self.spotify_manager = spotify_manager
        self.audio_manager = audio_manager
        self.playback_manager = playback_manager
        self.chromecast_manager = chromecast_manager
        self.background_manager = background_manager
        self.cec_manager = cec_manager
        self.image_manager = image_manager
        self.webcast_manager = webcast_manager
        self.chromium_manager = chromium_manager

        # Config
        self.ha_url: str = ""
        self.ha_token: str = ""
        self.entity_id: str = "media_player.hsg_canvas"
        self.enabled: bool = False
        self.automations: List[Dict[str, Any]] = []

        # Runtime state
        self._last_pushed_state: Optional[Dict[str, Any]] = None
        self._push_task: Optional[asyncio.Task] = None
        self._ws_task: Optional[asyncio.Task] = None
        self._ws_session: Optional[aiohttp.ClientSession] = None

    async def initialize(self):
        """Load config and start background tasks if configured"""
        self._load_config()
        if self.enabled and self.ha_url and self.ha_token:
            self._start_background_tasks()
        logging.info(f"HomeAssistant Manager initialized (enabled={self.enabled})")

    def _load_config(self):
        """Load configuration from YAML file"""
        try:
            if not Path(CONFIG_PATH).exists():
                self._save_config()
                return

            with open(CONFIG_PATH, "r") as f:
                config = yaml.safe_load(f) or {}

            self.ha_url = config.get("ha_url", "")
            self.ha_token = config.get("ha_token", "")
            self.entity_id = config.get("entity_id", "media_player.hsg_canvas")
            self.enabled = config.get("enabled", False)
            self.automations = config.get("automations", [])
            logging.info(f"Loaded HA config: url={self.ha_url}, enabled={self.enabled}, automations={len(self.automations)}")
        except Exception as e:
            logging.error(f"Failed to load HA config: {e}")

    def _save_config(self):
        """Save current configuration to YAML file"""
        try:
            config = {
                "ha_url": self.ha_url,
                "ha_token": self.ha_token,
                "entity_id": self.entity_id,
                "enabled": self.enabled,
                "automations": self.automations,
            }
            with open(CONFIG_PATH, "w") as f:
                yaml.dump(config, f, default_flow_style=False)
            logging.info("Saved HA config")
        except Exception as e:
            logging.error(f"Failed to save HA config: {e}")

    def _start_background_tasks(self):
        """Start the state push loop and WS listener"""
        if self._push_task is None or self._push_task.done():
            self._push_task = asyncio.create_task(self._state_push_loop())
        if self._ws_task is None or self._ws_task.done():
            self._ws_task = asyncio.create_task(self._ws_listener_loop())

    def _stop_background_tasks(self):
        """Cancel background tasks"""
        if self._push_task and not self._push_task.done():
            self._push_task.cancel()
            self._push_task = None
        if self._ws_task and not self._ws_task.done():
            self._ws_task.cancel()
            self._ws_task = None

    # -------------------------------------------------------------------------
    # HSG -> HA: State push
    # -------------------------------------------------------------------------

    def _aggregate_state(self) -> Dict[str, Any]:
        """Build HA-compatible state dict from all managers"""
        state = "idle"
        source = "idle"
        attrs = {
            "friendly_name": "HSG Canvas",
            "media_title": None,
            "media_artist": None,
            "media_album_name": None,
            "entity_picture": None,
            "volume_level": None,
            "source": "idle",
        }

        # Check Spotify
        if self.spotify_manager and self.spotify_manager.is_playing:
            state = "playing"
            source = "spotify"
            ti = self.spotify_manager.track_info
            attrs["media_title"] = ti.get("name")
            artists = ti.get("artists", "")
            if isinstance(artists, str):
                artists = artists.replace("\n", ", ")
            attrs["media_artist"] = artists
            attrs["media_album_name"] = ti.get("album")
            attrs["entity_picture"] = ti.get("album_art_url")
            attrs["source"] = "spotify"

        # Check audio stream
        elif self.audio_manager and self.audio_manager.current_audio_stream:
            state = "playing"
            source = "audio_stream"
            attrs["media_title"] = self.audio_manager.current_audio_stream
            attrs["source"] = "audio_stream"

        # Check video playback
        elif self.playback_manager and getattr(self.playback_manager, "current_stream", None):
            state = "playing"
            source = "youtube"
            attrs["source"] = "youtube"

        # Check Chromecast
        elif self.chromecast_manager and getattr(self.chromecast_manager, "is_casting", False):
            state = "playing"
            source = "chromecast"
            attrs["source"] = "chromecast"

        attrs["source"] = source
        return {"state": state, "attributes": attrs}

    async def _push_state_to_ha(self, state_data: Dict[str, Any]) -> bool:
        """Push state to HA REST API"""
        if not self.ha_url or not self.ha_token:
            return False

        url = f"{self.ha_url.rstrip('/')}/api/states/{self.entity_id}"
        headers = {
            "Authorization": f"Bearer {self.ha_token}",
            "Content-Type": "application/json",
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url, json=state_data, headers=headers,
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as resp:
                    if resp.status in (200, 201):
                        self._last_pushed_state = state_data
                        return True
                    else:
                        text = await resp.text()
                        logging.warning(f"HA state push failed ({resp.status}): {text}")
                        return False
        except Exception as e:
            logging.warning(f"HA state push error: {e}")
            return False

    async def _state_push_loop(self):
        """Background: poll state every 5s, push on change"""
        logging.info("HA state push loop started")
        while True:
            try:
                await asyncio.sleep(5)
                if not self.enabled:
                    continue

                current = self._aggregate_state()
                if current != self._last_pushed_state:
                    await self._push_state_to_ha(current)

            except asyncio.CancelledError:
                logging.info("HA state push loop stopped")
                break
            except Exception as e:
                logging.error(f"HA state push loop error: {e}")
                await asyncio.sleep(5)

    async def notify_state_change(self):
        """Immediate state push (called from Spotify events etc.)"""
        if not self.enabled:
            return
        try:
            current = self._aggregate_state()
            await self._push_state_to_ha(current)
        except Exception as e:
            logging.error(f"HA immediate push error: {e}")

    # -------------------------------------------------------------------------
    # HA -> HSG: WebSocket event subscription
    # -------------------------------------------------------------------------

    async def _ws_listener_loop(self):
        """Background: connect to HA WebSocket, subscribe to state_changed"""
        logging.info("HA WebSocket listener starting")

        while True:
            try:
                if not self.enabled or not self.ha_url or not self.ha_token:
                    await asyncio.sleep(10)
                    continue

                ws_url = self.ha_url.rstrip("/").replace("http://", "ws://").replace("https://", "wss://") + "/api/websocket"
                logging.info(f"Connecting to HA WebSocket: {ws_url}")

                async with aiohttp.ClientSession() as session:
                    async with session.ws_connect(ws_url) as ws:
                        # Step 1: receive auth_required
                        msg = await ws.receive_json()
                        if msg.get("type") != "auth_required":
                            logging.error(f"Unexpected HA WS message: {msg}")
                            continue

                        # Step 2: authenticate
                        await ws.send_json({
                            "type": "auth",
                            "access_token": self.ha_token,
                        })
                        msg = await ws.receive_json()
                        if msg.get("type") != "auth_ok":
                            logging.error(f"HA WS auth failed: {msg}")
                            await asyncio.sleep(30)
                            continue

                        logging.info("HA WebSocket authenticated")

                        # Step 3: subscribe to state_changed events
                        await ws.send_json({
                            "id": 1,
                            "type": "subscribe_events",
                            "event_type": "state_changed",
                        })
                        msg = await ws.receive_json()
                        if not msg.get("success"):
                            logging.error(f"HA WS subscribe failed: {msg}")
                            continue

                        logging.info("Subscribed to HA state_changed events")

                        # Step 4: listen for events
                        async for msg in ws:
                            if msg.type == aiohttp.WSMsgType.TEXT:
                                data = json.loads(msg.data)
                                if data.get("type") == "event":
                                    await self._handle_ha_event(data.get("event", {}))
                            elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                                logging.warning("HA WebSocket closed/error")
                                break

            except asyncio.CancelledError:
                logging.info("HA WebSocket listener stopped")
                break
            except Exception as e:
                logging.error(f"HA WebSocket error: {e}")

            # Reconnect delay
            logging.info("HA WebSocket reconnecting in 10s...")
            await asyncio.sleep(10)

    async def _handle_ha_event(self, event: Dict[str, Any]):
        """Match incoming HA state changes against automation rules"""
        event_data = event.get("data", {})
        entity_id = event_data.get("entity_id", "")
        new_state = event_data.get("new_state", {})
        old_state = event_data.get("old_state", {})

        new_val = new_state.get("state", "") if new_state else ""
        old_val = old_state.get("state", "") if old_state else ""

        for rule in self.automations:
            trigger_entity = rule.get("trigger_entity", "")
            trigger_from = rule.get("trigger_from", "")
            trigger_to = rule.get("trigger_to", "")

            if entity_id != trigger_entity:
                continue
            if trigger_from and old_val != trigger_from:
                continue
            if trigger_to and new_val != trigger_to:
                continue

            # Match found
            logging.info(f"HA automation matched: {entity_id} {old_val}->{new_val}, action={rule.get('action')}")
            await self._execute_action(rule.get("action", ""), rule.get("action_args", {}))

    async def _execute_action(self, action: str, args: Dict[str, Any]):
        """Execute a local manager action"""
        try:
            if action == "cec.tv_power_on":
                if self.cec_manager:
                    await self.cec_manager.power_on_tv()
            elif action == "cec.tv_power_off":
                if self.cec_manager:
                    await self.cec_manager.power_off_tv()
            elif action == "audio.start":
                if self.audio_manager:
                    await self.audio_manager.start_audio_stream(
                        args.get("stream_url", ""),
                        args.get("volume")
                    )
            elif action == "audio.stop":
                if self.audio_manager:
                    await self.audio_manager.stop_audio_stream()
            elif action == "audio.volume":
                if self.audio_manager:
                    await self.audio_manager.set_volume(args.get("volume", 50))
            elif action == "playback.youtube":
                if self.playback_manager:
                    await self.playback_manager.play_youtube(
                        args.get("youtube_url", ""),
                        args.get("duration"),
                        args.get("mute", False)
                    )
            elif action == "playback.stop":
                if self.playback_manager:
                    await self.playback_manager.stop_playback()
            elif action == "background.show":
                if self.background_manager:
                    await self.background_manager.start_static_mode_with_audio_status(show_audio_icon=False)
            elif action == "display.url":
                if self.chromium_manager:
                    await self.chromium_manager.start_kiosk(args.get("url", ""))
            elif action == "display.qrcode":
                if self.image_manager:
                    await self.image_manager.display_qr_code(
                        args.get("content", ""),
                        args.get("duration"),
                        self.background_manager
                    )
            elif action == "display.image":
                if self.image_manager:
                    await self.image_manager.save_and_display_image(
                        args.get("image_url", ""),
                        args.get("duration", 10),
                        self.background_manager
                    )
            elif action == "display.navigate":
                if self.background_manager:
                    mode = args.get("mode", "static")
                    if mode == "now-playing":
                        await self.background_manager.switch_to_now_playing()
                    else:
                        await self.background_manager.switch_to_static()
            elif action == "webcast.start":
                if self.webcast_manager:
                    from managers.webcast_manager import WebcastConfig
                    config = WebcastConfig(url=args.get("url", ""))
                    await self.webcast_manager.start_webcast(config)
            elif action == "webcast.stop":
                if self.webcast_manager:
                    await self.webcast_manager.stop_webcast()
            else:
                logging.warning(f"Unknown HA action: {action}")
                return

            logging.info(f"HA action executed: {action}")
        except Exception as e:
            logging.error(f"HA action {action} failed: {e}")

    # -------------------------------------------------------------------------
    # Configuration management
    # -------------------------------------------------------------------------

    async def update_config(self, ha_url: Optional[str] = None, ha_token: Optional[str] = None,
                            entity_id: Optional[str] = None, enabled: Optional[bool] = None) -> Dict[str, Any]:
        """Update HA connection settings"""
        if ha_url is not None:
            self.ha_url = ha_url.rstrip("/")
        if ha_token is not None:
            self.ha_token = ha_token
        if entity_id is not None:
            self.entity_id = entity_id
        if enabled is not None:
            self.enabled = enabled

        self._save_config()

        # Start or stop background tasks based on enabled state
        if self.enabled and self.ha_url and self.ha_token:
            self._start_background_tasks()
        else:
            self._stop_background_tasks()

        return self.get_status()

    async def test_connection(self) -> Dict[str, Any]:
        """Verify HA URL + token with GET /api/"""
        if not self.ha_url or not self.ha_token:
            return {"success": False, "message": "HA URL and token not configured"}

        url = f"{self.ha_url.rstrip('/')}/api/"
        headers = {
            "Authorization": f"Bearer {self.ha_token}",
            "Content-Type": "application/json",
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url, headers=headers,
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return {
                            "success": True,
                            "message": data.get("message", "API running"),
                            "ha_version": data.get("version"),
                        }
                    elif resp.status == 401:
                        return {"success": False, "message": "Invalid token (401 Unauthorized)"}
                    else:
                        text = await resp.text()
                        return {"success": False, "message": f"HTTP {resp.status}: {text}"}
        except aiohttp.ClientConnectorError:
            return {"success": False, "message": f"Cannot connect to {self.ha_url}"}
        except asyncio.TimeoutError:
            return {"success": False, "message": f"Connection timed out to {self.ha_url}"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def get_status(self) -> Dict[str, Any]:
        """Get current HA integration status"""
        return {
            "enabled": self.enabled,
            "ha_url": self.ha_url,
            "entity_id": self.entity_id,
            "has_token": bool(self.ha_token),
            "push_loop_running": self._push_task is not None and not self._push_task.done() if self._push_task else False,
            "ws_listener_running": self._ws_task is not None and not self._ws_task.done() if self._ws_task else False,
            "last_pushed_state": self._last_pushed_state.get("state") if self._last_pushed_state else None,
            "automations_count": len(self.automations),
        }

    def get_config(self) -> Dict[str, Any]:
        """Get config with token masked"""
        return {
            "ha_url": self.ha_url,
            "ha_token": ("*" * 8 + self.ha_token[-4:]) if len(self.ha_token) > 4 else "****" if self.ha_token else "",
            "entity_id": self.entity_id,
            "enabled": self.enabled,
            "automations": self.automations,
        }

    async def cleanup(self):
        """Cancel tasks, close connections"""
        logging.info("Cleaning up HomeAssistant Manager")
        self._stop_background_tasks()
        if self._ws_session and not self._ws_session.closed:
            await self._ws_session.close()
