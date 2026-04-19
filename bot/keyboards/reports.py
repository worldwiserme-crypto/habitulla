"""Report generation keyboards."""
from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def report_period_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📅 Bu hafta", callback_data="report:week"),
            InlineKeyboardButton(text="📅 Bu oy", callback_data="report:month"),
        ],
        [
            InlineKeyboardButton(text="📅 O'tgan hafta", callback_data="report:last_week"),
            InlineKeyboardButton(text="📅 O'tgan oy", callback_data="report:last_month"),
        ],
        [InlineKeyboardButton(text="📆 Boshqa sana", callback_data="report:custom")],
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel")],
    ])


def report_format_keyboard(period_code: str) -> InlineKeyboardMarkup:
    """Choose Excel or PDF (PDF is Premium)."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Excel", callback_data=f"format:{period_code}:excel")],
        [InlineKeyboardButton(text="📄 PDF + grafik (Premium)", callback_data=f"format:{period_code}:pdf")],
        [InlineKeyboardButton(text="◀️ Orqaga", callback_data="report:back")],
    ])
