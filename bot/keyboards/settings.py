"""Settings keyboards."""
from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def settings_main_keyboard(reminders_on: bool, currency: str) -> InlineKeyboardMarkup:
    bell = "🔔" if reminders_on else "🔕"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"💱 Valyuta: {currency}", callback_data="settings:currency")],
        [InlineKeyboardButton(text=f"{bell} Eslatmalar", callback_data="settings:reminders")],
        [InlineKeyboardButton(text="💎 Obuna holati", callback_data="settings:subscription")],
        [InlineKeyboardButton(text="🗑 Barcha ma'lumotni o'chirish", callback_data="settings:reset")],
        [InlineKeyboardButton(text="❌ Yopish", callback_data="cancel")],
    ])


def currency_keyboard() -> InlineKeyboardMarkup:
    currencies = ["UZS", "USD", "EUR", "RUB"]
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=c, callback_data=f"currency:{c}") for c in currencies],
        [InlineKeyboardButton(text="◀️ Orqaga", callback_data="settings:back")],
    ])


def reset_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚠️ Ha, hammasini o'chir", callback_data="reset:confirm")],
        [InlineKeyboardButton(text="◀️ Bekor qilish", callback_data="settings:back")],
    ])
