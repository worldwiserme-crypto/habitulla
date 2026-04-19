"""Inject user context into every handler."""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from bot.config import config
from bot.services.db_service import db
from bot.utils.logger import logger


class UserContextMiddleware(BaseMiddleware):
    """Auto-register users and inject user dict into handlers.

    Skips: messages in admin group (those are admin-originated).
    Blocks: banned users (sends notice once).
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        tg_user = None
        chat_id = None
        if isinstance(event, Message):
            tg_user = event.from_user
            chat_id = event.chat.id if event.chat else None
        elif isinstance(event, CallbackQuery):
            tg_user = event.from_user
            chat_id = event.message.chat.id if event.message and event.message.chat else None

        if tg_user is None:
            return await handler(event, data)

        # Skip DB work for bot messages in admin group (callback approval flow)
        # but still allow the handler to run
        if chat_id == config.admin_group_id and tg_user.id in config.admin_ids:
            data["user"] = {"id": tg_user.id, "is_admin": True}
            return await handler(event, data)

        try:
            user = await db.get_or_create_user(
                user_id=tg_user.id,
                username=tg_user.username,
                full_name=(tg_user.full_name or "").strip(),
            )
        except Exception as e:
            logger.error("User context failed for %s: %s", tg_user.id, e)
            user = {"id": tg_user.id, "currency": "UZS"}

        if user.get("is_banned"):
            try:
                if isinstance(event, Message):
                    await event.answer("🚫 Sizning akkauntingiz bloklangan.")
                elif isinstance(event, CallbackQuery):
                    await event.answer("🚫 Bloklangan", show_alert=True)
            except Exception:
                pass
            return None

        user["is_admin"] = tg_user.id in config.admin_ids
        data["user"] = user
        return await handler(event, data)
