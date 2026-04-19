"""Anti-spam throttling middleware (in-memory sliding window)."""
from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Any, Awaitable, Callable, Deque, Dict

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery

from bot.config import config
from bot.utils.logger import logger


class ThrottlingMiddleware(BaseMiddleware):
    """Allow N messages per 60 seconds per user. Notify once on violation."""

    def __init__(self, rate: int | None = None, window: int = 60) -> None:
        self.rate = rate or config.rate_limit_per_minute
        self.window = window
        self._hits: Dict[int, Deque[float]] = defaultdict(deque)
        self._notified: Dict[int, float] = {}

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user_id = None
        if isinstance(event, Message) and event.from_user:
            user_id = event.from_user.id
        elif isinstance(event, CallbackQuery) and event.from_user:
            user_id = event.from_user.id

        if user_id is None:
            return await handler(event, data)

        # Admins bypass
        if user_id in config.admin_ids:
            return await handler(event, data)

        now = time.time()
        hits = self._hits[user_id]
        while hits and now - hits[0] > self.window:
            hits.popleft()

        if len(hits) >= self.rate:
            last_notified = self._notified.get(user_id, 0)
            if now - last_notified > self.window:
                self._notified[user_id] = now
                try:
                    if isinstance(event, Message):
                        await event.answer(
                            "⚠️ Juda tez xabar yuboryapsiz. Biroz kuting."
                        )
                    elif isinstance(event, CallbackQuery):
                        await event.answer("⚠️ Juda tez!", show_alert=False)
                except Exception:
                    pass
            logger.debug("Throttled user %s", user_id)
            return None

        hits.append(now)
        return await handler(event, data)
