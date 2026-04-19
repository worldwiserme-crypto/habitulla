"""Input validation helpers."""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Optional

ALLOWED_CURRENCIES = {"UZS", "USD", "EUR", "RUB"}
ALLOWED_CATEGORIES = {
    "oziq-ovqat", "transport", "soglik", "kiyim",
    "kommunal", "ta'lim", "ko'ngil-ochar", "boshqa",
}
MAX_TEXT_LEN = 1000
MAX_HABIT_NAME_LEN = 200


def clean_text(text: str, max_len: int = MAX_TEXT_LEN) -> str:
    if not text:
        return ""
    text = text.strip()
    text = re.sub(r"\s+", " ", text)
    return text[:max_len]


def is_valid_currency(code: str) -> bool:
    return code.upper() in ALLOWED_CURRENCIES


def is_valid_category(category: str | None) -> bool:
    if not category:
        return True
    return category.lower() in ALLOWED_CATEGORIES


def normalize_date(value: str | None, today: date) -> date:
    """Convert 'today' / 'yesterday' / 'YYYY-MM-DD' → date."""
    if not value:
        return today
    value = value.strip().lower()
    if value in ("today", "bugun"):
        return today
    if value in ("yesterday", "kecha"):
        return today - timedelta(days=1)
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return today


def sanitize_amount(amount) -> Optional[float]:
    if amount is None:
        return None
    try:
        val = float(amount)
        if val < 0 or val > 1e12:
            return None
        return val
    except (TypeError, ValueError):
        return None


def sanitize_duration(duration) -> Optional[float]:
    if duration is None:
        return None
    try:
        val = float(duration)
        if val < 0 or val > 10000:
            return None
        return val
    except (TypeError, ValueError):
        return None
