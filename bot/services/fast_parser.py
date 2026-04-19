"""Fast regex-based parser for common Uzbek habit/budget messages.

Philosophy: ~70% of messages follow predictable patterns. Catching them
locally saves ~1-2 seconds and ~$0.0001 per message vs. calling Gemini.

NEW: If the message appears to contain MULTIPLE actions (e.g. "yugurdim. kitob
o'qidim. dush qabul qildim"), we return None so AI can parse all items.

Returns None if the message is ambiguous, letting AI handle it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

# ─── Amount patterns ───────────────────────────────────────────────
AMOUNT_RE = re.compile(
    r"(\d+(?:[\s.,]\d+)*)\s*(ming|mln|mlrd|million|milliard|k|m)?",
    re.IGNORECASE,
)
CURRENCY_HINTS = {
    "som": "UZS", "so'm": "UZS", "soum": "UZS", "sum": "UZS", "uzs": "UZS",
    "dollar": "USD", "usd": "USD", "$": "USD", "bucks": "USD",
    "euro": "EUR", "eur": "EUR", "€": "EUR",
    "rubl": "RUB", "rub": "RUB", "rur": "RUB",
}

# ─── Duration patterns ─────────────────────────────────────────────
DURATION_RE = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*(daqiqa|minut|min|soat|hour|marta|bet|km|kilometr)",
    re.IGNORECASE,
)

# ─── Keyword maps ──────────────────────────────────────────────────
EXPENSE_KEYWORDS = {
    "oldim", "xarid", "sotib", "to'ladim", "to'ladi", "chiqim",
    "berdim", "sarfladim", "sarf", "harjadim", "ishlatdim",
}
INCOME_KEYWORDS = {
    "oldim maosh", "maosh", "oylik", "bonus", "daromad", "kirim",
    "topdim", "ishladim", "pul oldim",
}

HABIT_KEYWORDS = {
    "yugurdim": "Yugurish",
    "yugurish": "Yugurish",
    "yurdim": "Yurish",
    "yurish": "Yurish",
    "qadam": "Yurish",
    "kitob": "Kitob o'qish",
    "o'qidim": "O'qish",
    "o'qish": "O'qish",
    "sport": "Sport",
    "sportzal": "Sportzal",
    "gym": "Sportzal",
    "mashq": "Mashq",
    "suv ichdim": "Suv ichish",
    "meditatsiya": "Meditatsiya",
    "namoz": "Namoz",
    "yoga": "Yoga",
    "ingliz": "Ingliz tili",
    "english": "Ingliz tili",
    "dars": "Dars",
    "velosiped": "Velosiped",
    "suzdim": "Suzish",
    "suzish": "Suzish",
    "dush": "Dush qabul qilish",
    "tish": "Tish yuvish",
}

# Verbs that indicate completed actions (helps count actions)
ACTION_VERBS = {
    "yugurdim", "yurdim", "o'qidim", "qildim", "qabul qildim", "ichdim",
    "bajardim", "suzdim", "ishladim", "mashq qildim", "yozdim",
    "eshitdim", "ko'rdim", "yedim", "tayyorladim",
}

CATEGORY_KEYWORDS = {
    "oziq-ovqat": ["non", "ovqat", "restoran", "kafe", "choyxona", "osh", "mahsulot",
                    "nonvoy", "supermarket", "bozor", "fast food", "pitsa", "burger",
                    "go'sht", "sabzavot", "meva", "choy", "kofe"],
    "transport": ["taksi", "yandex", "uber", "avtobus", "metro", "benzin", "yoqilg'i",
                   "marshrut", "poezd", "aeroport", "samolyot"],
    "soglik": ["dori", "shifokor", "klinika", "doktor", "analiz", "dorixona",
                "vitamin", "maslahat"],
    "kiyim": ["kiyim", "ko'ylak", "shim", "etik", "tuflik", "krossovka", "ko'ylakchi",
               "sumka", "paypoq"],
    "kommunal": ["svet", "elektr", "gaz", "suv", "internet", "telefon", "kommunal",
                  "arenda", "ijara", "wifi"],
    "ta'lim": ["kurs", "o'quv", "universitet", "maktab", "seminar",
                "webinar", "training"],
    "ko'ngil-ochar": ["kino", "teatr", "konsert", "o'yin", "gulzor", "park", "netflix",
                       "spotify", "youtube premium"],
}

DATE_KEYWORDS = {
    "bugun": "today",
    "hozir": "today",
    "kecha": "yesterday",
    "tong": "today",
    "kechqurun": "today",
}


@dataclass
class ParsedIntent:
    type: str  # HABIT_LOG | BUDGET_EXPENSE | BUDGET_INCOME | UNKNOWN
    habit_name: Optional[str] = None
    duration: Optional[float] = None
    duration_unit: Optional[str] = None
    amount: Optional[float] = None
    currency: Optional[str] = None
    category: Optional[str] = None
    date: str = "today"
    note: Optional[str] = None
    confidence: float = 0.0


def _parse_amount(text: str) -> tuple[Optional[float], Optional[str]]:
    """Extract amount + currency hint from text."""
    lower = text.lower()

    currency = None
    for hint, code in CURRENCY_HINTS.items():
        if hint in lower:
            currency = code
            break

    match = re.search(
        r"(\d+(?:[.,]\d+)?)\s*(ming|mln|mlrd|million|milliard|k|m|b)\b",
        lower,
    )
    if match:
        num = float(match.group(1).replace(",", "."))
        unit = match.group(2)
        multiplier = {
            "ming": 1_000, "k": 1_000,
            "mln": 1_000_000, "million": 1_000_000, "m": 1_000_000,
            "mlrd": 1_000_000_000, "milliard": 1_000_000_000, "b": 1_000_000_000,
        }.get(unit, 1)
        return num * multiplier, currency

    match = re.search(r"\b(\d{1,3}(?:[\s.,]\d{3})+|\d{4,})\b", text)
    if match:
        raw = match.group(1).replace(" ", "").replace(",", "").replace(".", "")
        try:
            return float(raw), currency
        except ValueError:
            return None, currency

    match = re.search(r"\b(\d+(?:\.\d+)?)\b", text)
    if match and currency:
        return float(match.group(1)), currency

    return None, currency


def _parse_duration(text: str) -> tuple[Optional[float], Optional[str]]:
    lower = text.lower()
    match = DURATION_RE.search(lower)
    if not match:
        return None, None
    value = float(match.group(1).replace(",", "."))
    unit_raw = match.group(2).lower()
    unit_map = {
        "daqiqa": "min", "minut": "min", "min": "min",
        "soat": "hour", "hour": "hour",
        "marta": "count",
        "bet": "page",
        "km": "km", "kilometr": "km",
    }
    return value, unit_map.get(unit_raw, unit_raw)


def _detect_category(text: str) -> Optional[str]:
    lower = text.lower()
    for cat, kws in CATEGORY_KEYWORDS.items():
        if any(kw in lower for kw in kws):
            return cat
    return None


def _detect_habit(text: str) -> Optional[str]:
    lower = text.lower()
    for kw, name in HABIT_KEYWORDS.items():
        if kw in lower:
            return name
    return None


def _detect_date(text: str) -> str:
    lower = text.lower()
    for kw, val in DATE_KEYWORDS.items():
        if kw in lower:
            return val
    return "today"


def _is_complex_message(text: str) -> bool:
    """Detect messages with MULTIPLE actions that need AI parsing.
    
    Heuristics:
    - Contains periods/commas + multiple verbs
    - Multiple duration markers
    - Multiple amount markers
    - Contains conjunctions like 'va', 'hamda', 'keyin'
    """
    lower = text.lower()
    
    # Count habit keywords present
    habit_count = sum(1 for kw in HABIT_KEYWORDS.keys() if kw in lower)
    
    # Count action verbs
    verb_count = sum(1 for v in ACTION_VERBS if v in lower)
    
    # Count sentence separators (period, semicolon, "va", "hamda", "keyin")
    separator_count = (
        text.count(".") + text.count(";") + text.count(",") +
        len(re.findall(r"\b(va|hamda|keyin|so'ng|yana)\b", lower))
    )
    
    # Count duration occurrences
    duration_count = len(DURATION_RE.findall(lower))
    
    # Count amount occurrences
    amount_count = len(re.findall(
        r"\d+\s*(?:ming|mln|k|m|so'm|som|$|\d{3,})",
        lower,
    ))
    
    # Complex if:
    # - 2+ habits mentioned
    # - 2+ action verbs
    # - 2+ durations
    # - 2+ amounts
    # - has separator AND (1+ habit or 1+ verb)
    if habit_count >= 2 or verb_count >= 2:
        return True
    if duration_count >= 2 or amount_count >= 2:
        return True
    if separator_count >= 1 and (habit_count >= 1 or verb_count >= 1):
        # Short single-clause like "Kitob 2 soat o'qidim." is NOT complex
        # But "Yugurdim. Kitobni o'qidim" IS complex
        # Heuristic: if original text has multiple clauses separated by period/semicolon
        clauses = [c.strip() for c in re.split(r"[.;]", text) if c.strip()]
        if len(clauses) >= 2:
            return True
    
    return False


def fast_parse(text: str) -> Optional[ParsedIntent]:
    """Try to parse without AI. Returns None if confidence too low OR message is complex."""
    if not text or len(text) < 2:
        return None

    lower = text.lower().strip()

    # Greeting / noise → let UNKNOWN handle
    if lower in {"salom", "hi", "hello", "assalomu alaykum", "/start", "/help"}:
        return None

    # NEW: Complex messages → defer to AI for multi-intent parsing
    if _is_complex_message(text):
        return None

    amount, currency = _parse_amount(text)
    duration, dur_unit = _parse_duration(text)
    habit = _detect_habit(text)
    category = _detect_category(text)
    date_val = _detect_date(text)

    has_income_kw = any(kw in lower for kw in INCOME_KEYWORDS)
    has_expense_kw = any(kw in lower for kw in EXPENSE_KEYWORDS)

    # ─── INCOME ─────────────────────────────────────────────
    if amount and has_income_kw and not has_expense_kw:
        return ParsedIntent(
            type="BUDGET_INCOME",
            amount=amount,
            currency=currency or "UZS",
            category=None,
            date=date_val,
            note=text[:200],
            confidence=0.9,
        )

    # ─── EXPENSE ────────────────────────────────────────────
    if amount and (has_expense_kw or category):
        return ParsedIntent(
            type="BUDGET_EXPENSE",
            amount=amount,
            currency=currency or "UZS",
            category=category or "boshqa",
            date=date_val,
            note=text[:200],
            confidence=0.9 if category else 0.75,
        )

    # ─── HABIT ──────────────────────────────────────────────
    if habit and (duration or "bajardim" in lower or "qildim" in lower):
        return ParsedIntent(
            type="HABIT_LOG",
            habit_name=habit,
            duration=duration,
            duration_unit=dur_unit,
            date=date_val,
            note=text[:200],
            confidence=0.9 if duration else 0.75,
        )

    # Amount without clear intent → likely expense (most common case)
    if amount and currency == "UZS" and amount >= 1000:
        return ParsedIntent(
            type="BUDGET_EXPENSE",
            amount=amount,
            currency=currency,
            category=category or "boshqa",
            date=date_val,
            note=text[:200],
            confidence=0.6,  # Low — triggers AI fallback
        )

    return None
