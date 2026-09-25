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

    # These display types are mutually exclusive — pushing one removes the others.
    # Prevents stale now-playing items from lingering when a new audio source takes over.
    EXCLUSIVE_TYPES = {"spotify", "sendspin", "bluetooth", "radio"}

    def __init__(self, on_change: Optional[Callable[['DisplayItem'], Coroutine]] = None):
        # BackgroundManager owns the base content and applies it at startup,
        # before the server accepts clients.
        self._base = DisplayItem("static", {}, item_id="base")
        self._stack: List[DisplayItem] = []
        self._on_change = on_change

    @property
    def current(self) -> DisplayItem:
        """Return the topmost item (or base if stack is empty)"""
        return self._stack[-1] if self._stack else self._base

    def get(self, item_id: str) -> Optional[DisplayItem]:
        """Return the item with this ID, or None"""
        return next((i for i in self._stack if i.id == item_id), None)

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
        # If item_id is given and already exists, update it instead of duplicating.
        # Always notify: the kiosk also renders items below the top (a video
        # under an overlay), so a change anywhere in the stack must reach it.
        existing = self.get(item_id) if item_id else None
        if existing:
            existing.content = content
            existing.type = item_type
            existing.duration = duration
            existing.pushed_at = time.time()
            self._start_expiry(existing)
            await self._notify_change()
            return existing

        # Evict mutually exclusive types (e.g. pushing spotify removes bluetooth/sendspin)
        if item_type in self.EXCLUSIVE_TYPES:
            rivals = [i for i in self._stack
                      if i.type in self.EXCLUSIVE_TYPES and i.type != item_type]
            for rival in rivals:
                self._cancel_expiry(rival)
                self._stack.remove(rival)
                logging.info(f"DisplayStack: evicted {rival.type} (id={rival.id}) for {item_type}")

        item = DisplayItem(item_type, content, duration, item_id)
        self._stack.append(item)
        self._start_expiry(item)

        await self._notify_change()
        logging.info(f"DisplayStack: pushed {item_type} (id={item.id}, duration={duration})")
        return item

    async def remove(self, item_id: str) -> bool:
        """Remove a specific item by ID"""
        item = self.get(item_id)
        if not item:
            return False
        self._cancel_expiry(item)
        self._stack.remove(item)
        await self._notify_change()
        logging.info(f"DisplayStack: removed {item.type} (id={item_id})")
        return True

    async def remove_by_type(self, item_type: str) -> int:
        """Remove all items of a given type. Returns count removed."""
        to_remove = [item for item in self._stack if item.type == item_type]
        for item in to_remove:
            self._cancel_expiry(item)
            self._stack.remove(item)

        if to_remove:
            logging.info(f"DisplayStack: removed {len(to_remove)} items of type {item_type}")
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
            # Detach first: remove() cancels the expiry task, and this task must
            # not cancel itself before the change broadcast completes.
            item._expiry_task = None
            await self.remove(item.id)
            logging.info(f"DisplayStack: item {item.id} ({item.type}) expired after {item.duration}s")
        except asyncio.CancelledError:
            pass

    def _start_expiry(self, item: DisplayItem):
        """(Re)start the item's expiry timer from its current duration"""
        self._cancel_expiry(item)
        if item.duration and item.duration > 0:
            item._expiry_task = asyncio.create_task(self._expire_item(item))

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
