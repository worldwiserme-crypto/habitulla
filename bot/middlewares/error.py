"""Global error-catching middleware.

Prevents any unhandled exception from crashing the bot.
Logs full traceback + sends friendly notice to the user.
"""
from __future__ import annotations

import traceback
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from bot.services.db_service import db
from bot.utils.logger import logger


class ErrorMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        try:
            return await handler(event, data)
        except Exception as e:
            tb = traceback.format_exc()
            logger.error("Unhandled exception: %s\n%s", e, tb)

            user_id = None
            if isinstance(event, (Message, CallbackQuery)) and event.from_user:
                user_id = event.from_user.id

            try:
                await db.log_metric(
                    "error",
                    user_id=user_id,
                    metadata={"error": str(e)[:500], "type": type(e).__name__},
                )
            except Exception:
                pass

            try:
                if isinstance(event, Message):
                    await event.answer("⚠️ Kutilmagan xatolik yuz berdi. Qayta urinib ko'ring.")
                elif isinstance(event, CallbackQuery):
                    await event.answer("⚠️ Xatolik", show_alert=True)
            except Exception:
                pass
            return None
