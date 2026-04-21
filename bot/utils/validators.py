"""Input validation and sanitization utilities."""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Optional


# Bullet/list markers and other noise at the start of text
_LEADING_NOISE = re.compile(r"^[\s•●○◦▪▫■□★☆→►▶▸▪️🔹🔸📌\-\*\+]+")

# Trailing punctuation noise
_TRAILING_NOISE = re.compile(r"[\s\-\*]+$")

# Multiple whitespace → single space
_MULTI_SPACE = re.compile(r"\s+")


def clean_text(text: str) -> str:
    """Clean user input: remove bullet points, extra whitespace, leading noise.
    
    Examples:
        '• Bugun yugurdim' → 'Bugun yugurdim'
        '  → 30 daqiqa yugurdim  ' → '30 daqiqa yugurdim'
        'Yugurdim\n\n\nkitob o\'qidim' → 'Yugurdim. kitob o'qidim'
    """
    if not text:
        return ""
    
    # Telegram HTML escapes
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    
    # Replace multiple newlines with period + space (for multi-line inputs)
    text = re.sub(r"\n{2,}", ". ", text)
    text = text.replace("\n", ". ")
    
    # Remove leading bullets/markers
    text = _LEADING_NOISE.sub("", text)
    
    # Clean up double periods from newline replacement
    text = re.sub(r"\.+\s*\.+", ".", text)
    text = re.sub(r"\.\s*\.", ".", text)
    
    # Normalize whitespace
    text = _MULTI_SPACE.sub(" ", text)
    
    # Trailing noise
    text = _TRAILING_NOISE.sub("", text)
    
    return text.strip()


def sanitize_amount(amount) -> Optional[float]:
    """Convert amount to float, handling various formats."""
    if amount is None:
        return None
    try:
        if isinstance(amount, (int, float)):
            return float(amount) if amount > 0 else None
        if isinstance(amount, str):
            cleaned = re.sub(r"[^\d.,]", "", amount)
            cleaned = cleaned.replace(",", ".")
            # Handle multiple dots (use last as decimal)
            parts = cleaned.split(".")
            if len(parts) > 2:
                cleaned = "".join(parts[:-1]) + "." + parts[-1]
            val = float(cleaned)
            return val if val > 0 else None
    except (ValueError, TypeError):
        return None
    return None


def sanitize_duration(duration) -> Optional[float]:
    """Convert duration to float."""
    if duration is None:
        return None
    try:
        if isinstance(duration, (int, float)):
            return float(duration) if duration > 0 else None
        if isinstance(duration, str):
            cleaned = re.sub(r"[^\d.,]", "", duration)
            cleaned = cleaned.replace(",", ".")
            val = float(cleaned)
            return val if val > 0 else None
    except (ValueError, TypeError):
        return None
    return None


def normalize_date(date_str: Optional[str], today: date) -> date:
    """Convert date string (today/yesterday/YYYY-MM-DD) to date object."""
    if not date_str:
        return today
    
    date_str = str(date_str).lower().strip()
    
    if date_str in ("today", "bugun", "hozir"):
        return today
    if date_str in ("yesterday", "kecha"):
        return today - timedelta(days=1)
    
    # Try YYYY-MM-DD
    try:
        return date.fromisoformat(date_str)
    except (ValueError, TypeError):
        pass
    
    # Try datetime ISO format
    try:
        return datetime.fromisoformat(date_str).date()
    except (ValueError, TypeError):
        pass
    
    return today


def validate_user_id(user_id) -> Optional[int]:
    """Validate and convert user ID to int."""
    try:
        uid = int(user_id)
        if uid > 0:
            return uid
    except (ValueError, TypeError):
        pass
    return None


def truncate(text: str, max_length: int = 200) -> str:
    """Truncate text with ellipsis."""
    if not text:
        return ""
    text = text.strip()
    if len(text) <= max_length:
        return text
    return text[: max_length - 3] + "..."
