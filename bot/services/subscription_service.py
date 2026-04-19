"""Subscription tier logic (manual approval flow)."""
from __future__ import annotations

from datetime import datetime
from typing import Tuple

from bot.config import config
from bot.services.db_service import db


async def is_premium(user_id: int) -> bool:
    """Check if user has active premium subscription."""
    if user_id in config.admin_ids:
        return True

    sub = await db.get_subscription(user_id)
    if sub.get("tier") != "premium":
        return False
    expires = sub.get("expires_at")
    if not expires:
        return False
    try:
        exp_dt = datetime.fromisoformat(str(expires).replace("Z", "+00:00"))
        exp_dt = exp_dt.replace(tzinfo=None)
    except (ValueError, AttributeError):
        return False
    return exp_dt > datetime.utcnow()


async def check_daily_limit(user_id: int) -> Tuple[bool, int, int]:
    """Returns (allowed, current_count, limit). Premium = unlimited (-1)."""
    if await is_premium(user_id):
        return True, 0, -1

    count = await db.get_today_usage(user_id)
    limit = config.free_daily_log_limit
    return count < limit, count, limit


async def can_use_voice(user_id: int) -> bool:
    return await is_premium(user_id)


async def can_use_custom_date_range(user_id: int, days: int) -> bool:
    if await is_premium(user_id):
        return True
    return days <= config.free_report_max_days


async def can_use_pdf_reports(user_id: int) -> bool:
    return await is_premium(user_id)


async def can_use_ai_insights(user_id: int) -> bool:
    return await is_premium(user_id)


async def get_subscription_status_text(user_id: int) -> str:
    if user_id in config.admin_ids:
        return "👑 Administrator"

    sub = await db.get_subscription(user_id)
    if sub.get("tier") != "premium":
        return "🆓 Bepul tarif"

    expires = sub.get("expires_at")
    try:
        exp_dt = datetime.fromisoformat(str(expires).replace("Z", "+00:00"))
        exp_dt = exp_dt.replace(tzinfo=None)
    except (ValueError, AttributeError):
        return "🆓 Bepul tarif"

    if exp_dt <= datetime.utcnow():
        return "🆓 Bepul tarif (obuna muddati tugagan)"

    days_left = (exp_dt - datetime.utcnow()).days
    return f"💎 Premium — yana {days_left} kun"
