"""
Shared route helper utilities.

Reduces boilerplate in the route modules for manager operations.
"""
import logging
from typing import Coroutine

from fastapi import HTTPException


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
