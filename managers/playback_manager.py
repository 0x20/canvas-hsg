"""
Playback Manager

Handles video playback (YouTube, streams) via the display stack.
YouTube videos are played in the browser via the YouTube IFrame API.
"""
import asyncio
import logging
import re
from typing import Optional

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

    async def stop_playback(self) -> bool:
        """Stop current playback by removing from display stack"""
        try:
            if self.current_protocol == "youtube":
                await self.display_stack.remove("youtube")

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
