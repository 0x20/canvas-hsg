"""Radio station list routes (the control panel's Radio tab and its editor)."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from models.request_models import StationsRequest


class DetectRequest(BaseModel):
    url: str


def setup_stations_routes(station_store, station_art=None, on_saved=None,
                          track_info=None, resolve_url=None) -> APIRouter:
    router = APIRouter(prefix="/stations", tags=["stations"])

    @router.get("")
    async def get_stations():
        """All groups and stations, in display order."""
        return station_store.get()

    @router.put("")
    async def save_stations(request: StationsRequest):
        """Replace the list: reorder, add, remove, regroup.

        A station whose logo URL changed loses its cached logo, so the
        background lookup fetches it again with the new URL first.
        """
        old_images = {s["url"]: s.get("image") for s in station_store.stations()}
        try:
            data = station_store.save(request.model_dump(exclude_none=True))
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        if station_art:
            for station in station_store.stations():
                if station["url"] in old_images and station.get("image") != old_images[station["url"]]:
                    station_art.clear(station["url"])
        if on_saved:
            on_saved()
        return data

    @router.post("/detect")
    async def detect_track_info(request: DetectRequest):
        """Probe one station again for how to read its playing track (takes up to a minute)."""
        station = station_store.by_url(request.url)
        if not station or not track_info:
            raise HTTPException(status_code=404, detail="No station with this URL")
        resolved = await resolve_url(station["url"]) if resolve_url else station["url"]
        method = await track_info.detect(station["url"], resolved, [station["name"]])
        station_store.set_track_info(station["url"], method)
        return method

    return router
