"""'Mening kabinetim' handler — user profile, stats overview, subscription info."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.keyboards.common import BTN_CABINET
from bot.services.analytics_service import compute_streak
from bot.services.db_service import db
from bot.services.subscription_service import (
    check_daily_limit,
    get_subscription_status_text,
    is_premium,
)
from bot.utils.formatters import format_amount, format_date

router = Router(name="cabinet")


async def _build_cabinet_text(user: dict) -> str:
    user_id = user["id"]
    currency = user.get("currency") or "UZS"
    status = await get_subscription_status_text(user_id)

    habit_stats = await db.get_habit_stats(user_id)
    budget_stats = await db.get_budget_stats(user_id)
    streak = await compute_streak(user_id)
    is_prem = await is_premium(user_id)
    allowed, count, limit = await check_daily_limit(user_id)

    limit_line = "♾ Cheksiz" if limit == -1 else f"{count} / {limit}"
    month_balance = budget_stats["month_income"] - budget_stats["month_expense"]
    balance_emoji = "✅" if month_balance >= 0 else "⚠️"

    return (
        "👤 <b>Mening kabinetim</b>\n\n"
        f"📛 <b>Ism:</b> {user.get('full_name') or '—'}\n"
        f"💎 <b>Obuna:</b> {status}\n"
        f"💱 <b>Valyuta:</b> {currency}\n"
        f"📅 <b>Ro'yxatdan:</b> {str(user.get('created_at', ''))[:10]}\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "📊 <b>BUGUN</b>\n"
        f"  🎯 Odatlar: <b>{habit_stats['today']}</b>\n"
        f"  💸 Chiqim: <b>{format_amount(budget_stats['today_expense'], currency)}</b>\n"
        f"  💰 Kirim: <b>{format_amount(budget_stats['today_income'], currency)}</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "📈 <b>BU OY</b>\n"
        f"  🎯 Odatlar: <b>{habit_stats['month']}</b>\n"
        f"  💸 Chiqim: <b>{format_amount(budget_stats['month_expense'], currency)}</b>\n"
        f"  💰 Kirim: <b>{format_amount(budget_stats['month_income'], currency)}</b>\n"
        f"  {balance_emoji} Qoldiq: <b>{format_amount(month_balance, currency)}</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"🔥 <b>Streak:</b> {streak} kun\n"
        f"🚦 <b>Kunlik limit:</b> {limit_line}\n\n"
        "<i>Batafsil sozlash: /settings</i>"
    )


@router.message(Command("cabinet"))
@router.message(F.text == BTN_CABINET)
async def cmd_cabinet(message: Message, user: dict) -> None:
    text = await _build_cabinet_text(user)
    await message.answer(text, parse_mode="HTML")
