"""
Now-playing resolver

One place that decides which source owns the now-playing view and builds the
track payload, so the WebSocket hydration, the live broadcasts and the small
kiosk view always agree.
"""
from typing import Any, Dict, Optional, Tuple


def track_payload(info: Dict[str, Any], paused: bool = False) -> Dict[str, Any]:
    """The `track_changed` data for a manager's track_info dict."""
    artists = info.get("artists") or info.get("artist") or "Unknown Artist"
    if isinstance(artists, list):
        artists = ", ".join(artists)
    return {
        "name": info.get("name"),
        "artists": artists.replace("\n", ", "),
        "album": info.get("album") or "",
        "album_art_url": info.get("album_art_url"),
        "duration_ms": info.get("duration_ms") or 0,
        "spotify_url": info.get("spotify_url"),
        "paused": paused,
    }


class NowPlaying:
    """Resolves the active now-playing source across all audio managers."""

    def __init__(self, spotify_manager=None, sendspin_manager=None,
                 bluetooth_manager=None, audio_manager=None):
        self.spotify_manager = spotify_manager
        self.sendspin_manager = sendspin_manager
        self.bluetooth_manager = bluetooth_manager
        self.audio_manager = audio_manager

    def current(self) -> Optional[Tuple[str, Dict[str, Any]]]:
        """(source, payload) of the source that owns the view, or None.

        A paused source still owns the view (held card), so it counts too.
        """
        for source, manager in (("spotify", self.spotify_manager),
                                ("sendspin", self.sendspin_manager),
                                ("bluetooth", self.bluetooth_manager)):
            if not manager:
                continue
            paused = bool(getattr(manager, "is_paused", False))
            info = manager.track_info or {}
            if (manager.is_playing or paused) and info.get("name"):
                return source, track_payload(info, paused)
        # A radio stream: live track when the stream sends metadata, otherwise
        # the station name.
        if self.audio_manager:
            payload = self.audio_manager.now_playing_payload()
            if payload:
                return "radio", payload
        return None

    def initial_event(self) -> Optional[Dict[str, Any]]:
        """The track_changed event for a client that just connected."""
        current = self.current()
        if not current:
            return None
        return {"event": "track_changed", "data": current[1]}

    def kiosk_track(self) -> Dict[str, Any]:
        """Flat track dict for the small kiosk panels.

        When nothing plays, shows the last known Spotify track.
        """
        current = self.current()
        if current:
            source, data = current
        elif self.spotify_manager and self.spotify_manager.track_info:
            source, data = "spotify-idle", track_payload(self.spotify_manager.track_info)
        else:
            source, data = "static", {}
        return {
            "name": data.get("name") or "",
            "artists": data.get("artists") or "",
            "album": data.get("album") or "",
            "album_art_url": data.get("album_art_url") or "",
            "source": source,
        }
