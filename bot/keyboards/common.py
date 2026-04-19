"""Common keyboards — 4-button main menu per product vision."""
from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

# Main menu button labels (used in F.text filters in handlers)
BTN_HABIT = "🎯 Odat Tracker"
BTN_BUDGET = "💰 Budjet Tracker"
BTN_CABINET = "👤 Mening kabinetim"
BTN_REPORTS = "📊 Hisobotlar"


def main_reply_keyboard() -> ReplyKeyboardMarkup:
    """Always-visible bottom menu. 4 buttons in 2 rows."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_HABIT), KeyboardButton(text=BTN_BUDGET)],
            [KeyboardButton(text=BTN_CABINET), KeyboardButton(text=BTN_REPORTS)],
        ],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Matn yoki ovoz yuboring...",
    )


def cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel")]
    ])


def confirmation_keyboard(confirm_data: str, cancel_data: str = "cancel") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Ha", callback_data=confirm_data),
            InlineKeyboardButton(text="❌ Yo'q", callback_data=cancel_data),
        ]
    ])


def remove_keyboard() -> ReplyKeyboardRemove:
    return ReplyKeyboardRemove()
