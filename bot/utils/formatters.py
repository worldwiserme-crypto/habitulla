"""Formatting helpers for Uzbek locale."""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

import pytz

from bot.config import config

TZ = pytz.timezone(config.timezone)

UZ_MONTHS = [
    "Yanvar", "Fevral", "Mart", "Aprel", "May", "Iyun",
    "Iyul", "Avgust", "Sentabr", "Oktabr", "Noyabr", "Dekabr",
]

UZ_WEEKDAYS = [
    "Dushanba", "Seshanba", "Chorshanba", "Payshanba",
    "Juma", "Shanba", "Yakshanba",
]


def format_amount(amount: float | int | None, currency: str = "UZS") -> str:
    """Format amount with thousand separators."""
    if amount is None:
        return f"0 {currency}"
    try:
        amount = float(amount)
    except (TypeError, ValueError):
        return f"0 {currency}"

    if amount == int(amount):
        formatted = f"{int(amount):,}".replace(",", " ")
    else:
        formatted = f"{amount:,.2f}".replace(",", " ")
    return f"{formatted} {currency}"


def format_duration(duration: float | int | None, unit: str | None) -> str:
    """Format habit duration like '30 daqiqa' or '2 soat'."""
    if duration is None:
        return "bajarildi"

    try:
        duration = float(duration)
    except (TypeError, ValueError):
        return str(duration)

    value = int(duration) if duration == int(duration) else round(duration, 1)

    unit_map = {
        "min": "daqiqa",
        "minute": "daqiqa",
        "minutes": "daqiqa",
        "daqiqa": "daqiqa",
        "hour": "soat",
        "hours": "soat",
        "soat": "soat",
        "count": "marta",
        "marta": "marta",
        "page": "bet",
        "pages": "bet",
        "bet": "bet",
        "km": "km",
    }
    uz_unit = unit_map.get((unit or "").lower(), unit or "")
    return f"{value} {uz_unit}".strip()


def format_date(d: date | datetime, with_weekday: bool = False) -> str:
    """Format date as '18 Aprel 2026' or with weekday."""
    if isinstance(d, datetime):
        if d.tzinfo is None:
            d = pytz.UTC.localize(d)
        d = d.astimezone(TZ).date()

    base = f"{d.day} {UZ_MONTHS[d.month - 1]} {d.year}"
    if with_weekday:
        base = f"{UZ_WEEKDAYS[d.weekday()]}, {base}"
    return base


def today_local() -> date:
    return datetime.now(TZ).date()


def now_local() -> datetime:
    return datetime.now(TZ)


CATEGORY_EMOJIS = {
    "oziq-ovqat": "🍞",
    "transport": "🚗",
    "soglik": "💊",
    "kiyim": "👕",
    "kommunal": "💡",
    "ta'lim": "📚",
    "ko'ngil-ochar": "🎭",
    "boshqa": "📦",
}


def category_label(category: str | None) -> str:
    if not category:
        return "📦 Boshqa"
    emoji = CATEGORY_EMOJIS.get(category.lower(), "📦")
    return f"{emoji} {category.capitalize()}"


def truncate(text: str, max_len: int = 50) -> str:
    if not text:
        return ""
    return text if len(text) <= max_len else text[: max_len - 1] + "…"
