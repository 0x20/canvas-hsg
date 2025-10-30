"""
Stream Routes

Handles stream republishing to SRS server (RTMP/HLS/HTTP-FLV).
"""
from typing import TYPE_CHECKING

from fastapi import APIRouter, HTTPException

if TYPE_CHECKING:
    from managers.stream_manager import StreamManager

router = APIRouter()


def setup_stream_routes(stream_manager: 'StreamManager') -> APIRouter:
    """
    Setup stream routes with dependency injection

    Args:
        stream_manager: StreamManager instance for stream republishing

    Returns:
        Configured APIRouter
    """

    @router.post("/streams/{stream_key}/start")
    async def start_stream(stream_key: str, source_url: str, protocol: str = "rtmp"):
        """Start publishing a GPU-accelerated stream using specified protocol"""
        success = await stream_manager.start_stream(stream_key, source_url, protocol)
        if success:
            return {"message": f"GPU-accelerated stream {stream_key} started via {protocol.upper()}"}
        else:
            raise HTTPException(status_code=500, detail=f"Failed to start {protocol} stream")

    @router.delete("/streams/{stream_key}")
    async def stop_stream(stream_key: str):
        """Stop a specific stream"""
        success = await stream_manager.stop_stream(stream_key)
        if success:
            return {"message": f"Stream {stream_key} stopped"}
        else:
            raise HTTPException(status_code=404, detail="Stream not found")

    @router.get("/streams")
    async def list_streams():
        """List all active streams"""
        streams = {}
        for key, info in stream_manager.active_streams.items():
            streams[key] = {
                "source_url": info["source_url"],
                "protocol": info["protocol"],
                "started_at": info["started_at"],
                "status": info["status"]
            }

        return {
            "active_streams": streams,
            "stream_count": len(streams)
        }

    return router
