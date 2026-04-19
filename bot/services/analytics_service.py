"""Analytics & aggregation helpers."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, timedelta
from typing import Any, Dict, List

from bot.services.db_service import db
from bot.utils.formatters import today_local


async def habit_summary(user_id: int, start: date, end: date) -> Dict[str, Any]:
    logs = await db.get_habits_in_range(user_id, start, end)
    counter: Counter = Counter()
    total_by_habit: Dict[str, float] = defaultdict(float)
    by_date: Dict[str, int] = defaultdict(int)

    for log in logs:
        name = log.get("habit_name") or "Noma'lum"
        counter[name] += 1
        if log.get("duration") is not None:
            total_by_habit[name] += float(log["duration"])
        by_date[str(log.get("logged_date"))] += 1

    top_habits = [
        {"name": n, "count": c, "total_duration": total_by_habit[n]}
        for n, c in counter.most_common(5)
    ]
    days_active = len(by_date)
    days_total = max((end - start).days + 1, 1)

    return {
        "total_logs": len(logs),
        "unique_habits": len(counter),
        "top_habits": top_habits,
        "days_active": days_active,
        "days_total": days_total,
        "consistency_pct": round((days_active / days_total) * 100, 1),
    }


async def budget_summary(user_id: int, start: date, end: date) -> Dict[str, Any]:
    logs = await db.get_budget_in_range(user_id, start, end)
    total_income = 0.0
    total_expense = 0.0
    by_category: Dict[str, float] = defaultdict(float)
    expense_count = 0

    for log in logs:
        amount = float(log.get("amount") or 0)
        if log.get("type") == "income":
            total_income += amount
        else:
            total_expense += amount
            expense_count += 1
            cat = log.get("category") or "boshqa"
            by_category[cat] += amount

    balance = total_income - total_expense
    top_categories = sorted(
        by_category.items(), key=lambda kv: kv[1], reverse=True
    )[:5]

    days = max((end - start).days + 1, 1)
    avg_daily_expense = total_expense / days

    return {
        "total_income": total_income,
        "total_expense": total_expense,
        "balance": balance,
        "expense_count": expense_count,
        "top_categories": top_categories,
        "avg_daily_expense": avg_daily_expense,
        "days": days,
    }


async def compute_streak(user_id: int, max_days: int = 90) -> int:
    """Current consecutive-day streak of habit logging."""
    today = today_local()
    start = today - timedelta(days=max_days - 1)
    logs = await db.get_habits_in_range(user_id, start, today)

    dates = {str(log.get("logged_date")) for log in logs}
    streak = 0
    cur = today
    while cur.isoformat() in dates:
        streak += 1
        cur = cur - timedelta(days=1)
    return streak
