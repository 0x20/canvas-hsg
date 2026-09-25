"""Radio station list routes (the control panel's Radio tab and its editor)."""
from fastapi import APIRouter, HTTPException

from models.request_models import StationsRequest


def setup_stations_routes(station_store, on_saved=None) -> APIRouter:
    router = APIRouter(prefix="/stations", tags=["stations"])

    @router.get("")
    async def get_stations():
        """All groups and stations, in display order."""
        return station_store.get()

    @router.put("")
    async def save_stations(request: StationsRequest):
        """Replace the list: reorder, add, remove, regroup."""
        try:
            data = station_store.save(request.model_dump(exclude_none=True))
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        if on_saved:
            on_saved()
        return data

    return router
