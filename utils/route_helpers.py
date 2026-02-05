"""
Shared route helper utilities.

Reduces boilerplate in routes.py for controller validation and manager operations.
"""
import logging
from typing import Any, Coroutine

from fastapi import HTTPException


def require_video_controller(playback_manager):
    """
    Validate that a video controller is available and connected.

    Args:
        playback_manager: PlaybackManager instance

    Returns:
        The connected video controller

    Raises:
        HTTPException: If no controller available or not connected
    """
    if not playback_manager.video_controller:
        raise HTTPException(status_code=404, detail="No active playback")
    controller = playback_manager.video_controller
    if not controller.connected:
        raise HTTPException(status_code=500, detail="Playback controller not available")
    return controller


async def manager_operation(
    coro: Coroutine,
    success_response: dict,
    failure_detail: str,
    error_context: str = "operation",
) -> dict:
    """
    Execute a manager operation with standard error handling.

    Args:
        coro: Awaitable coroutine to execute
        success_response: Dict to return on success
        failure_detail: Detail message for failure HTTPException
        error_context: Context string for error logging

    Returns:
        success_response dict on success

    Raises:
        HTTPException: On failure or error
    """
    try:
        result = await coro
        if result:
            return success_response
        else:
            raise HTTPException(status_code=500, detail=failure_detail)
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Failed to {error_context}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
