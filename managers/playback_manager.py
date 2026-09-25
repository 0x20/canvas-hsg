"""
Playback Manager

Handles video playback (YouTube, Twitch, streams) via the display stack.
YouTube videos are played in the browser via the YouTube IFrame API;
Twitch channels/VODs/clips via the Twitch embedded player iframe.
"""
import logging
import re
from typing import Optional
from urllib.parse import urlparse


# Display stack item IDs of the video players
VIDEO_ITEM_IDS = ("youtube", "twitch")


class PlaybackManager:
    """Manages video playback via the display stack.

    The display stack is the only record of what plays: a video item is on
    the stack while it plays, and the kiosk removes it when the video ends.
    """

    def __init__(self, display_stack, audio_conflict=None):
        self.display_stack = display_stack
        self.audio_conflict = audio_conflict

    def _video_item(self):
        """The video item on the display stack, or None"""
        for item_id in VIDEO_ITEM_IDS:
            item = self.display_stack.get(item_id)
            if item:
                return item
        return None

    @property
    def is_playing(self) -> bool:
        return self._video_item() is not None

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
        video_id = self._extract_youtube_video_id(youtube_url)
        if not video_id:
            logging.error(f"Could not extract YouTube video ID from: {youtube_url}")
            return False
        return await self._play("youtube", {"video_id": video_id, "url": youtube_url, "mute": mute},
                                duration, mute)

    async def play_twitch(self, twitch_url: str, duration: Optional[int] = None, mute: bool = False) -> bool:
        """Play a Twitch channel/VOD/clip via the display stack (rendered by React TwitchPlayer)"""
        info = self._parse_twitch_url(twitch_url)
        if not info:
            logging.error(f"Could not parse Twitch URL: {twitch_url}")
            return False
        return await self._play("twitch", {"kind": info["kind"], "twitch_id": info["id"],
                                           "url": twitch_url, "mute": mute},
                                duration, mute)

    async def _play(self, kind: str, content: dict, duration: Optional[int], mute: bool) -> bool:
        try:
            # A video with sound is an audio source: silence the others
            if self.audio_conflict:
                if mute:
                    await self.audio_conflict.release("video")
                else:
                    await self.audio_conflict.claim("video")

            # Push first, then drop the other player. The stack always holds
            # a video in between, so the audio claim is not released.
            await self.display_stack.push(kind, content, duration=duration, item_id=kind)
            for item_id in VIDEO_ITEM_IDS:
                if item_id != kind:
                    await self.display_stack.remove(item_id)
            logging.info(f"{kind} pushed to display stack: {content['url']}")
            return True
        except Exception as e:
            logging.error(f"{kind} playback failed: {e}")
            return False

    async def stop_playback(self) -> bool:
        """Stop current playback by removing from display stack"""
        try:
            for item_id in VIDEO_ITEM_IDS:
                await self.display_stack.remove(item_id)
            await self.on_stack_change()
            return True
        except Exception as e:
            logging.error(f"Failed to stop playback: {e}")
            return False

    async def on_stack_change(self) -> None:
        """Release the audio when no video is left (it ended or was removed)."""
        if self.audio_conflict and not self.is_playing:
            await self.audio_conflict.release("video")

    def get_playback_status(self) -> dict:
        item = self._video_item()
        return {
            "is_playing": item is not None,
            "current_stream": f"{item.type}:{item.content.get('url')}" if item else None,
            "protocol": item.type if item else None,
            "player": "browser" if item else None,
        }
