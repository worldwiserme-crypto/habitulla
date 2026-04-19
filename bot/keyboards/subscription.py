"""Subscription-related keyboards."""
from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.config import config
from bot.utils.formatters import format_amount


def plan_selection_keyboard() -> InlineKeyboardMarkup:
    """Show available subscription plans."""
    rows = []
    for code, plan in config.plans.items():
        rows.append([
            InlineKeyboardButton(
                text=f"{plan.name_uz} — {format_amount(plan.price_uzs, 'UZS')}",
                callback_data=f"plan:{code}",
            )
        ])
    rows.append([InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def upload_receipt_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Planni o'zgartirish", callback_data="back_to_plans")],
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel")],
    ])


def admin_approval_keyboard(request_id: int) -> InlineKeyboardMarkup:
    """Shown in admin group under each receipt."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"approve:{request_id}"),
            InlineKeyboardButton(text="❌ Rad etish", callback_data=f"reject:{request_id}"),
        ],
        [
            InlineKeyboardButton(text="ℹ️ User ma'lumotlari", callback_data=f"user_info:{request_id}"),
        ],
    ])


def rejection_reasons_keyboard(request_id: int) -> InlineKeyboardMarkup:
    """Predefined rejection reasons."""
    reasons = [
        ("Chek ko'rinmadi", "unclear"),
        ("Summa noto'g'ri", "wrong_amount"),
        ("Chek soxta", "fake"),
        ("Boshqa (yozib beraman)", "custom"),
    ]
    rows = [
        [InlineKeyboardButton(text=label, callback_data=f"reject_reason:{request_id}:{code}")]
        for label, code in reasons
    ]
    rows.append([InlineKeyboardButton(text="◀️ Orqaga", callback_data=f"back_approval:{request_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
