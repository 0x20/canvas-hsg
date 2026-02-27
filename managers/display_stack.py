"""
Display Stack

Core abstraction for managing layered display items.
Replaces ad-hoc mode tracking with a proper stack-based model.

The stack has a persistent base layer (static background) and items
pushed on top (Spotify, images, YouTube, websites, etc.).
The topmost item is what's displayed. When items expire or are removed,
the next item down (or the base) becomes visible.
"""
import asyncio
import logging
import time
import uuid
from typing import Any, Callable, Coroutine, Dict, List, Optional


class DisplayItem:
    """A single display layer"""

    def __init__(self, item_type: str, content: Dict[str, Any],
                 duration: Optional[int] = None, item_id: Optional[str] = None):
        self.id: str = item_id or str(uuid.uuid4())[:8]
        self.type: str = item_type
        self.content: Dict[str, Any] = content
        self.duration: Optional[int] = duration
        self.pushed_at: float = time.time()
        self._expiry_task: Optional[asyncio.Task] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "content": self.content,
            "duration": self.duration,
            "pushed_at": self.pushed_at,
        }


class DisplayStack:
    """
    Manages a stack of display items with a persistent base layer.

    The base is always present (static background). Items are pushed
    on top and the topmost item is the current display. Items can
    have durations (auto-expire) or be persistent until removed.
    """

    def __init__(self, on_change: Optional[Callable[['DisplayItem'], Coroutine]] = None):
        self._base = DisplayItem("static", {"background_url": "/static/canvas_background.png"}, item_id="base")
        self._stack: List[DisplayItem] = []
        self._on_change = on_change

    @property
    def current(self) -> DisplayItem:
        """Return the topmost item (or base if stack is empty)"""
        return self._stack[-1] if self._stack else self._base

    def get_stack(self) -> List[Dict[str, Any]]:
        """Return the full stack state for API inspection"""
        items = [self._base.to_dict()]
        for item in self._stack:
            items.append(item.to_dict())
        return items

    async def push(self, item_type: str, content: Dict[str, Any],
                   duration: Optional[int] = None, item_id: Optional[str] = None) -> DisplayItem:
        """Push a new item onto the display stack.

        Args:
            item_type: Type of display (spotify, image, qrcode, youtube, website, video)
            content: Type-specific content dict
            duration: Optional auto-expire duration in seconds
            item_id: Optional fixed ID (for idempotent pushes like "spotify")
        """
        # If item_id is given and already exists, update it instead of duplicating
        if item_id:
            for existing in self._stack:
                if existing.id == item_id:
                    existing.content = content
                    existing.type = item_type
                    existing.pushed_at = time.time()
                    # If it's the top item, notify
                    if existing is self.current:
                        await self._notify_change()
                    return existing

        item = DisplayItem(item_type, content, duration, item_id)
        self._stack.append(item)

        # Start expiry timer if duration is set
        if duration and duration > 0:
            item._expiry_task = asyncio.create_task(self._expire_item(item))

        await self._notify_change()
        logging.info(f"DisplayStack: pushed {item_type} (id={item.id}, duration={duration})")
        return item

    async def remove(self, item_id: str) -> bool:
        """Remove a specific item by ID"""
        for i, item in enumerate(self._stack):
            if item.id == item_id:
                was_top = (i == len(self._stack) - 1)
                self._cancel_expiry(item)
                self._stack.pop(i)
                if was_top:
                    await self._notify_change()
                logging.info(f"DisplayStack: removed {item.type} (id={item_id})")
                return True
        return False

    async def remove_by_type(self, item_type: str) -> int:
        """Remove all items of a given type. Returns count removed."""
        was_top_type = self.current.type if self._stack else None
        to_remove = [item for item in self._stack if item.type == item_type]
        for item in to_remove:
            self._cancel_expiry(item)
            self._stack.remove(item)

        if to_remove:
            logging.info(f"DisplayStack: removed {len(to_remove)} items of type {item_type}")
            # Only notify if the top changed
            new_top_type = self.current.type if self._stack else None
            if was_top_type == item_type or new_top_type != was_top_type:
                await self._notify_change()

        return len(to_remove)

    async def pop(self) -> Optional[DisplayItem]:
        """Remove and return the top item"""
        if not self._stack:
            return None
        item = self._stack.pop()
        self._cancel_expiry(item)
        await self._notify_change()
        logging.info(f"DisplayStack: popped {item.type} (id={item.id})")
        return item

    async def clear(self):
        """Remove everything above the base"""
        for item in self._stack:
            self._cancel_expiry(item)
        self._stack.clear()
        await self._notify_change()
        logging.info("DisplayStack: cleared all items")

    async def update_base_content(self, content: Dict[str, Any]):
        """Update the base layer content (background image)"""
        self._base.content = content
        # Only notify if base is currently showing
        if not self._stack:
            await self._notify_change()
        logging.info(f"DisplayStack: base content updated")

    async def _expire_item(self, item: DisplayItem):
        """Wait for duration then remove the item"""
        try:
            await asyncio.sleep(item.duration)
            await self.remove(item.id)
            logging.info(f"DisplayStack: item {item.id} ({item.type}) expired after {item.duration}s")
        except asyncio.CancelledError:
            pass

    def _cancel_expiry(self, item: DisplayItem):
        """Cancel an item's expiry timer if active"""
        if item._expiry_task and not item._expiry_task.done():
            item._expiry_task.cancel()
            item._expiry_task = None

    async def _notify_change(self):
        """Fire the on_change callback with the new current item"""
        if self._on_change:
            try:
                await self._on_change(self.current)
            except Exception as e:
                logging.error(f"DisplayStack: on_change callback error: {e}")
