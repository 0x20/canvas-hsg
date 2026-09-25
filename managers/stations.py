"""
Radio stations: the groups and stations the control panel shows.

The list lives in state/stations.json so the panel can edit it on the Pi
without changing a file that git tracks. On the first start it is copied
from the music_streams section of media_sources.yaml.
"""
import json
import logging
import os
from typing import Any, Dict, Iterator, List, Optional

from utils.media_sources import load_media_sources

STATIONS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "state", "stations.json"
)

# Display names for the YAML group keys; other keys are title-cased
_GROUP_NAMES = {"somafm": "SomaFM", "bbc": "BBC"}

# Station fields that are kept; anything else in the YAML is dropped
_STATION_FIELDS = ("name", "url", "image", "description")


def _group_name(key: str) -> str:
    return _GROUP_NAMES.get(key, key.replace("_", " ").title())


def _seed_from_yaml() -> Dict[str, Any]:
    groups = []
    for key, stations in (load_media_sources().get("music_streams") or {}).items():
        groups.append({
            "name": _group_name(key),
            "stations": [
                {f: s[f] for f in _STATION_FIELDS if s.get(f)}
                for s in stations or [] if s.get("name") and s.get("url")
            ],
        })
    return {"groups": groups}


class StationStore:
    """Loads, saves and looks up the station list. Kept in memory after the first read."""

    def __init__(self, path: str = STATIONS_PATH):
        self.path = path
        self._data: Optional[Dict[str, Any]] = None

    def get(self) -> Dict[str, Any]:
        if self._data is None:
            try:
                with open(self.path) as f:
                    self._data = json.load(f)
            except FileNotFoundError:
                self._data = _seed_from_yaml()
                self._write(self._data)
                logging.info(f"Station list created from media_sources.yaml at {self.path}")
            except (OSError, ValueError) as e:
                logging.error(f"Station list {self.path} unreadable, using media_sources.yaml: {e}")
                self._data = _seed_from_yaml()
        return self._data

    def save(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Replace the list. The caller validates the shape (see StationsRequest)."""
        # Keep a detected track-info method when the URL did not change: an
        # editor that loaded before the detection finished sends none.
        known = {s["url"]: s["track_info"] for s in self.stations() if s.get("track_info")}
        for station in self._iter(data):
            if "track_info" not in station and station.get("url") in known:
                station["track_info"] = known[station["url"]]
        seen = set()
        for station in self._iter(data):
            if station["url"] in seen:
                raise ValueError(f"The URL {station['url']} is in the list twice")
            seen.add(station["url"])
        self._write(data)
        self._data = data
        return data

    def stations(self) -> Iterator[Dict[str, Any]]:
        return self._iter(self.get())

    def set_track_info(self, url: str, method: Dict[str, Any]) -> bool:
        """Save the detected track-info method on the station with this URL."""
        station = self.by_url(url)
        if not station:
            return False
        station["track_info"] = method
        self._write(self._data)
        return True

    def by_url(self, url: str) -> Optional[Dict[str, Any]]:
        return next((s for s in self.stations() if s["url"] == url), None)

    def as_media_sources(self) -> Dict[str, List[Dict[str, Any]]]:
        """The list in the old media_sources music_streams shape: {group: [station]}."""
        return {g["name"]: g["stations"] for g in self.get()["groups"]}

    @staticmethod
    def _iter(data: Dict[str, Any]) -> Iterator[Dict[str, Any]]:
        for group in data.get("groups", []):
            yield from group.get("stations", [])

    def _write(self, data: Dict[str, Any]) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, self.path)
