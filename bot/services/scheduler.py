"""APScheduler jobs: daily/weekly/monthly reports + subscription expiry check."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import FSInputFile
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from bot.config import config
from bot.services.analytics_service import budget_summary, compute_streak, habit_summary
from bot.services.db_service import db
from bot.services.excel_service import cleanup_file, generate_excel_report
from bot.utils.formatters import UZ_MONTHS, format_amount, format_date, today_local
from bot.utils.logger import logger


# ═════════════════════ DAILY ═════════════════════
async def send_daily_summary(bot: Bot) -> None:
    try:
        users = await db.get_users_with_reminders()
    except Exception as e:
        logger.error("Failed to fetch reminder users: %s", e)
        return

    logger.info("Sending daily reminders to %d users", len(users))
    ok = fail = 0
    for user in users:
        user_id = user["id"]
        currency = user.get("currency") or "UZS"
        try:
            habit_stats = await db.get_habit_stats(user_id)
            budget_stats = await db.get_budget_stats(user_id)
            streak = await compute_streak(user_id)

            streak_line = f"\n🔥 Ketma-ket: <b>{streak}</b> kun" if streak > 0 else ""

            text = (
                "🌙 <b>Bugungi xulosa:</b>\n\n"
                f"✅ Odatlar: <b>{habit_stats['today']}</b> ta\n"
                f"💸 Xarajat: <b>{format_amount(budget_stats['today_expense'], currency)}</b>\n"
                f"💰 Kirim: <b>{format_amount(budget_stats['today_income'], currency)}</b>"
                f"{streak_line}\n\n"
                "Ertaga ham davom eting! 💪"
            )
            await bot.send_message(user_id, text, parse_mode="HTML")
            ok += 1
            await asyncio.sleep(0.05)
        except TelegramAPIError as e:
            fail += 1
            logger.debug("Skip reminder for %s: %s", user_id, e)
        except Exception as e:
            fail += 1
            logger.warning("Reminder failed for %s: %s", user_id, e)
    logger.info("Daily reminders: ok=%d fail=%d", ok, fail)


# ═════════════════════ WEEKLY ═════════════════════
async def send_weekly_report(bot: Bot) -> None:
    try:
        users = await db.get_users_with_reminders()
    except Exception as e:
        logger.error("Failed to fetch users for weekly report: %s", e)
        return

    today = today_local()
    start = today - timedelta(days=6)
    logger.info("Sending weekly reports to %d users (%s — %s)", len(users), start, today)

    for user in users:
        user_id = user["id"]
        currency = user.get("currency") or "UZS"
        try:
            habit_stats, budget_stats, streak = await asyncio.gather(
                habit_summary(user_id, start, today),
                budget_summary(user_id, start, today),
                compute_streak(user_id),
            )

            if habit_stats["total_logs"] == 0 and budget_stats["total_expense"] == 0:
                # Don't spam inactive users
                continue

            top_habits = "\n".join(
                f"  • {h['name']}: <b>{h['count']}</b> marta"
                for h in habit_stats["top_habits"][:3]
            ) or "  • Ma'lumot yo'q"

            top_cats = "\n".join(
                f"  • {c}: <b>{format_amount(a, currency)}</b>"
                for c, a in budget_stats["top_categories"][:3]
            ) or "  • Ma'lumot yo'q"

            balance = budget_stats["balance"]
            balance_emoji = "✅" if balance >= 0 else "⚠️"

            text = (
                "📊 <b>Haftalik hisobot</b>\n"
                f"<i>{format_date(start)} — {format_date(today)}</i>\n\n"
                f"🔥 Streak: <b>{streak}</b> kun\n"
                f"📅 Faol kunlar: <b>{habit_stats['days_active']}/7</b> ({habit_stats['consistency_pct']}%)\n\n"
                f"<b>Odatlar:</b> {habit_stats['total_logs']} ta\n{top_habits}\n\n"
                f"<b>Kirim:</b> {format_amount(budget_stats['total_income'], currency)}\n"
                f"<b>Chiqim:</b> {format_amount(budget_stats['total_expense'], currency)}\n"
                f"{balance_emoji} <b>Qoldiq:</b> {format_amount(balance, currency)}\n\n"
                f"<b>Top kategoriyalar:</b>\n{top_cats}\n\n"
                "To'liq Excel hisobot uchun: /report"
            )
            await bot.send_message(user_id, text, parse_mode="HTML")
            await asyncio.sleep(0.08)
        except TelegramAPIError as e:
            logger.debug("Skip weekly for %s: %s", user_id, e)
        except Exception as e:
            logger.warning("Weekly report failed for %s: %s", user_id, e)


# ═════════════════════ MONTHLY ═════════════════════
async def send_monthly_report(bot: Bot) -> None:
    """Send Excel report for previous month on 1st day."""
    try:
        users = await db.get_users_with_reminders()
    except Exception as e:
        logger.error("Failed to fetch users for monthly: %s", e)
        return

    today = today_local()
    first_of_this_month = today.replace(day=1)
    end = first_of_this_month - timedelta(days=1)
    start = end.replace(day=1)

    month_name = UZ_MONTHS[start.month - 1]
    logger.info("Sending monthly reports for %s %d", month_name, start.year)

    for user in users:
        user_id = user["id"]
        try:
            # Check if user has any data in that month
            habit_logs = await db.get_habits_in_range(user_id, start, end)
            budget_logs = await db.get_budget_in_range(user_id, start, end)
            if not habit_logs and not budget_logs:
                continue

            path = await generate_excel_report(user_id, start, end)
            try:
                caption = (
                    f"📈 <b>{month_name} {start.year} — oylik hisobot</b>\n\n"
                    "Ushbu faylda barcha odatlar va budjet ma'lumotlari."
                )
                await bot.send_document(
                    user_id,
                    FSInputFile(path, filename=f"hisobot_{month_name}_{start.year}.xlsx"),
                    caption=caption,
                    parse_mode="HTML",
                )
                await asyncio.sleep(0.2)
            finally:
                cleanup_file(path)
        except TelegramAPIError as e:
            logger.debug("Skip monthly for %s: %s", user_id, e)
        except Exception as e:
            logger.warning("Monthly report failed for %s: %s", user_id, e)


# ═════════════════════ SUBSCRIPTION EXPIRY ═════════════════════
async def check_expiring_subscriptions(bot: Bot) -> None:
    """Notify users whose premium expires in 3 days / tomorrow / today."""
    # Implementation: iterate active premiums and match expiry date
    from bot.services.cache_service import subscription_cache
    subscription_cache._cache.clear()

    try:
        users = await db.get_all_active_user_ids()
    except Exception as e:
        logger.error("Expiry check fetch failed: %s", e)
        return

    now = datetime.utcnow()
    for user_id in users:
        try:
            sub = await db.get_subscription(user_id)
            if sub.get("tier") != "premium":
                continue
            expires = sub.get("expires_at")
            if not expires:
                continue
            try:
                exp_dt = datetime.fromisoformat(str(expires).replace("Z", "+00:00"))
                exp_dt = exp_dt.replace(tzinfo=None)
            except (ValueError, AttributeError):
                continue

            hours_left = (exp_dt - now).total_seconds() / 3600
            if 71 <= hours_left <= 73:  # ~3 days
                await bot.send_message(
                    user_id,
                    "⏰ <b>Premium obunangiz 3 kundan so'ng tugaydi</b>\n\n"
                    "Davom ettirish uchun: /premium",
                    parse_mode="HTML",
                )
            elif 23 <= hours_left <= 25:  # ~1 day
                await bot.send_message(
                    user_id,
                    "⚠️ <b>Premium obunangiz ertaga tugaydi</b>\n\n"
                    "Uzaytirish uchun: /premium",
                    parse_mode="HTML",
                )
            await asyncio.sleep(0.05)
        except TelegramAPIError:
            pass
        except Exception as e:
            logger.debug("Expiry check error for %s: %s", user_id, e)


# ═════════════════════ SETUP ═════════════════════
def setup_scheduler(bot: Bot) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=config.timezone)

    scheduler.add_job(
        send_daily_summary,
        CronTrigger(
            hour=config.daily_reminder_hour,
            minute=config.daily_reminder_minute,
            timezone=config.timezone,
        ),
        args=[bot],
        id="daily_summary",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    scheduler.add_job(
        send_weekly_report,
        CronTrigger(
            day_of_week=config.weekly_report_weekday,
            hour=config.weekly_report_hour,
            minute=0,
            timezone=config.timezone,
        ),
        args=[bot],
        id="weekly_report",
        replace_existing=True,
        misfire_grace_time=3600 * 6,
    )

    scheduler.add_job(
        send_monthly_report,
        CronTrigger(
            day=config.monthly_report_day,
            hour=config.monthly_report_hour,
            minute=0,
            timezone=config.timezone,
        ),
        args=[bot],
        id="monthly_report",
        replace_existing=True,
        misfire_grace_time=3600 * 12,
    )

    scheduler.add_job(
        check_expiring_subscriptions,
        CronTrigger(hour=10, minute=0, timezone=config.timezone),
        args=[bot],
        id="expiry_check",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    return scheduler
