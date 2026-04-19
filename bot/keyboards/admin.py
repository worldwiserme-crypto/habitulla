"""Admin panel keyboards."""
from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def admin_main_keyboard(pending_count: int = 0) -> InlineKeyboardMarkup:
    pending_label = f"📥 Kutilayotgan to'lovlar ({pending_count})" if pending_count else "📥 Kutilayotgan to'lovlar"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Statistika", callback_data="admin:stats")],
        [InlineKeyboardButton(text=pending_label, callback_data="admin:pending")],
        [InlineKeyboardButton(text="🔍 User qidirish", callback_data="admin:find_user")],
        [InlineKeyboardButton(text="📢 Broadcast yuborish", callback_data="admin:broadcast")],
        [InlineKeyboardButton(text="💰 Daromad hisoboti", callback_data="admin:revenue")],
        [InlineKeyboardButton(text="🔄 Yangilash", callback_data="admin:refresh")],
        [InlineKeyboardButton(text="❌ Yopish", callback_data="cancel")],
    ])


def back_to_admin_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Admin panelga qaytish", callback_data="admin:refresh")],
    ])


def user_action_keyboard(user_id: int, is_banned: bool = False) -> InlineKeyboardMarkup:
    ban_btn = (
        InlineKeyboardButton(text="✅ Bloklashni olib tashlash", callback_data=f"admin_user:unban:{user_id}")
        if is_banned
        else InlineKeyboardButton(text="🚫 Bloklash", callback_data=f"admin_user:ban:{user_id}")
    )
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💎 Premium berish (30 kun)", callback_data=f"admin_user:grant:{user_id}")],
        [ban_btn],
        [InlineKeyboardButton(text="◀️ Orqaga", callback_data="admin:refresh")],
    ])


def broadcast_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Yuborish", callback_data="broadcast:send")],
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="broadcast:cancel")],
    ])
