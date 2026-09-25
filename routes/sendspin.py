"""Sendspin (Music Assistant) routes."""
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response


def setup_sendspin_routes(sendspin_manager) -> APIRouter:
    router = APIRouter(prefix="/sendspin", tags=["sendspin"])

    @router.get("/status")
    async def get_sendspin_status():
        """Get Sendspin connection and playback status"""
        return sendspin_manager.get_status()

    @router.post("/hook/start")
    async def sendspin_hook_start():
        """Called by sendspin daemon --hook-start when audio stream starts."""
        await sendspin_manager.handle_hook_start()
        return {"status": "ok"}

    @router.post("/hook/stop")
    async def sendspin_hook_stop():
        """Called by sendspin daemon --hook-stop when audio stream stops."""
        await sendspin_manager.handle_hook_stop()
        return {"status": "ok"}

    @router.get("/artwork")
    async def get_sendspin_artwork():
        """Serve the latest album art received from Music Assistant via the
        Sendspin ARTWORK display client (binary frames over the LAN, no external
        URL). Cache-busted by the ?v= version in the broadcast art URL."""
        client = getattr(sendspin_manager, "artwork_client", None)
        if client is None or not client.art_bytes:
            raise HTTPException(status_code=404, detail="No artwork available")
        return Response(
            content=client.art_bytes,
            media_type=client.art_mime,
            headers={"Cache-Control": "no-cache"},
        )

    return router
