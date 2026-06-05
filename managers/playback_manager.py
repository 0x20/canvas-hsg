"""
Playback Manager

Handles video playback (YouTube, Twitch, streams) via the display stack.
YouTube videos are played in the browser via the YouTube IFrame API;
Twitch channels/VODs/clips via the Twitch embedded player iframe.
"""
import asyncio
import logging
import re
from typing import Optional
from urllib.parse import urlparse

from utils.drm import get_optimal_connector_and_device as _get_optimal_connector_and_device


class PlaybackManager:
    """Manages video playback via the display stack"""

    def __init__(self, display_stack, display_detector, background_manager=None, audio_manager=None):
        self.display_stack = display_stack
        self.display_detector = display_detector
        self.background_manager = background_manager
        self.audio_manager = audio_manager

        # Current playback state (for status reporting)
        self.current_stream: Optional[str] = None
        self.current_protocol: Optional[str] = None
        self.current_player: Optional[str] = None

        # Keep for backward compat with routes that check this
        self.video_controller = None

    def get_optimal_connector_and_device(self) -> tuple[str, str]:
        return _get_optimal_connector_and_device(self.display_detector)

    @staticmethod
    def _extract_youtube_video_id(url: str) -> Optional[str]:
        """Extract video ID from various YouTube URL formats"""
        patterns = [
            r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)([a-zA-Z0-9_-]{11})',
            r'youtube\.com/shorts/([a-zA-Z0-9_-]{11})',
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None

    @staticmethod
    def _parse_twitch_url(url: str) -> Optional[dict]:
        """
        Parse a Twitch URL into the embed parameters the player needs.

        Returns a dict {"kind": "channel"|"video"|"clip", "id": ...} or None
        if the URL isn't a recognisable Twitch URL. Handles:
          - twitch.tv/<channel>            → live channel
          - twitch.tv/videos/<id>          → VOD
          - twitch.tv/<channel>/clip/<slug>→ clip
          - clips.twitch.tv/<slug>         → clip
        """
        parsed = urlparse(url)
        host = parsed.netloc.lower()
        if not (host == "twitch.tv" or host.endswith(".twitch.tv")):
            return None

        parts = [p for p in parsed.path.split("/") if p]

        # clips.twitch.tv/<slug>
        if host.startswith("clips."):
            return {"kind": "clip", "id": parts[0]} if parts else None
        # twitch.tv/<channel>/clip/<slug>
        if len(parts) >= 3 and parts[1] == "clip":
            return {"kind": "clip", "id": parts[2]}
        # twitch.tv/videos/<id>
        if len(parts) >= 2 and parts[0] == "videos":
            return {"kind": "video", "id": parts[1]}
        # twitch.tv/<channel>
        if parts and parts[0] not in ("directory", "settings", "subscriptions"):
            return {"kind": "channel", "id": parts[0]}
        return None

    async def play_url(self, url: str, duration: Optional[int] = None, mute: bool = False) -> bool:
        """Play a video URL, dispatching to the right platform by URL shape."""
        if self._parse_twitch_url(url):
            return await self.play_twitch(url, duration=duration, mute=mute)
        return await self.play_youtube(url, duration=duration, mute=mute)

    async def play_youtube(self, youtube_url: str, duration: Optional[int] = None, mute: bool = False) -> bool:
        """Play YouTube video via the display stack (rendered by React YouTubePlayer)"""
        try:
            # Stop any existing playback
            if self.current_stream:
                await self.stop_playback()

            # Stop audio stream if YouTube is playing with audio
            if not mute and self.audio_manager:
                await self.audio_manager.stop_audio_stream()

            # Extract video ID from URL
            video_id = self._extract_youtube_video_id(youtube_url)
            if not video_id:
                logging.error(f"Could not extract YouTube video ID from: {youtube_url}")
                return False

            logging.info(f"Playing YouTube video via display stack: {youtube_url} (video_id={video_id})")

            await self.display_stack.push(
                "youtube",
                {"video_id": video_id, "url": youtube_url, "mute": mute},
                duration=duration,
                item_id="youtube",
            )

            self.current_stream = f"youtube:{youtube_url}"
            self.current_protocol = "youtube"
            self.current_player = "browser"

            logging.info(f"YouTube video pushed to display stack: {youtube_url}")
            return True

        except Exception as e:
            logging.error(f"YouTube playback failed: {e}")
            return False

    async def play_twitch(self, twitch_url: str, duration: Optional[int] = None, mute: bool = False) -> bool:
        """Play a Twitch channel/VOD/clip via the display stack (rendered by React TwitchPlayer)"""
        try:
            # Stop any existing playback
            if self.current_stream:
                await self.stop_playback()

            # Stop audio stream if Twitch is playing with audio
            if not mute and self.audio_manager:
                await self.audio_manager.stop_audio_stream()

            info = self._parse_twitch_url(twitch_url)
            if not info:
                logging.error(f"Could not parse Twitch URL: {twitch_url}")
                return False

            logging.info(f"Playing Twitch {info['kind']} via display stack: {twitch_url} (id={info['id']})")

            await self.display_stack.push(
                "twitch",
                {"kind": info["kind"], "twitch_id": info["id"], "url": twitch_url, "mute": mute},
                duration=duration,
                item_id="twitch",
            )

            self.current_stream = f"twitch:{twitch_url}"
            self.current_protocol = "twitch"
            self.current_player = "browser"

            logging.info(f"Twitch stream pushed to display stack: {twitch_url}")
            return True

        except Exception as e:
            logging.error(f"Twitch playback failed: {e}")
            return False

    async def stop_playback(self) -> bool:
        """Stop current playback by removing from display stack"""
        try:
            if self.current_protocol in ("youtube", "twitch"):
                await self.display_stack.remove(self.current_protocol)

            self.current_stream = None
            self.current_protocol = None
            self.current_player = None

            logging.info("Playback stopped")
            return True
        except Exception as e:
            logging.error(f"Failed to stop playback: {e}")
            return False

    def get_playback_status(self) -> dict:
        is_playing = self.current_stream is not None
        return {
            "is_playing": is_playing,
            "current_stream": self.current_stream if is_playing else None,
            "protocol": self.current_protocol if is_playing else None,
            "player": self.current_player if is_playing else None,
        }
