"""Handler decorators: @admin_only, @premium_only, @admin_group_only."""
from __future__ import annotations

from functools import wraps
from typing import Any, Callable

from aiogram.types import CallbackQuery, Message

from bot.config import config
from bot.services.subscription_service import is_premium


def admin_only(handler: Callable) -> Callable:
    """Only allow users listed in ADMIN_IDS."""
    @wraps(handler)
    async def wrapper(event, *args, **kwargs):
        user_id = event.from_user.id if event.from_user else None
        if user_id not in config.admin_ids:
            if isinstance(event, Message):
                await event.answer("⛔️ Bu buyruq faqat adminlar uchun.")
            elif isinstance(event, CallbackQuery):
                await event.answer("⛔️ Faqat adminlar uchun", show_alert=True)
            return None
        return await handler(event, *args, **kwargs)
    return wrapper


def admin_group_only(handler: Callable) -> Callable:
    """Only handle events in the admin approval group."""
    @wraps(handler)
    async def wrapper(event, *args, **kwargs):
        chat_id = None
        if isinstance(event, Message) and event.chat:
            chat_id = event.chat.id
        elif isinstance(event, CallbackQuery) and event.message and event.message.chat:
            chat_id = event.message.chat.id

        if chat_id != config.admin_group_id:
            if isinstance(event, CallbackQuery):
                await event.answer("Bu funksiya faqat admin guruhida", show_alert=True)
            return None

        user_id = event.from_user.id if event.from_user else None
        if user_id not in config.admin_ids:
            if isinstance(event, CallbackQuery):
                await event.answer("⛔️ Ruxsat yo'q", show_alert=True)
            return None
        return await handler(event, *args, **kwargs)
    return wrapper


def premium_only(feature_name: str = "Bu funksiya") -> Callable:
    """Block non-premium users from a handler."""
    def decorator(handler: Callable) -> Callable:
        @wraps(handler)
        async def wrapper(event, *args, **kwargs):
            user_id = event.from_user.id if event.from_user else None
            if not user_id or not await is_premium(user_id):
                msg = (
                    f"💎 <b>{feature_name} faqat Premium foydalanuvchilar uchun</b>\n\n"
                    "Premium olish uchun: /premium"
                )
                if isinstance(event, Message):
                    await event.answer(msg, parse_mode="HTML")
                elif isinstance(event, CallbackQuery):
                    await event.answer(f"💎 {feature_name} — Premium", show_alert=True)
                return None
            return await handler(event, *args, **kwargs)
        return wrapper
    return decorator
