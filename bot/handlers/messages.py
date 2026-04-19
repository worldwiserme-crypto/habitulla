"""Main message handler: text + voice parsing with context modes.

Context modes (activated via main menu buttons):
  • habit_mode  — AI biased toward habit logs
  • budget_mode — AI biased toward budget logs
  • no state    — auto-detect (fallback)
"""
from __future__ import annotations

import os
import tempfile

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot.keyboards.common import (
    BTN_BUDGET,
    BTN_CABINET,
    BTN_HABIT,
    BTN_REPORTS,
)
from bot.services.ai_service import AIServiceError, ai
from bot.services.db_service import db
from bot.services.fast_parser import ParsedIntent
from bot.services.subscription_service import can_use_voice, check_daily_limit
from bot.states.user_states import TrackerModes
from bot.utils.formatters import (
    category_label,
    format_amount,
    format_duration,
    today_local,
)
from bot.utils.logger import logger
from bot.utils.validators import (
    clean_text,
    normalize_date,
    sanitize_amount,
    sanitize_duration,
)

router = Router(name="messages")


# ═════════════════════ MAIN MENU BUTTONS ═════════════════════
@router.message(F.text == BTN_HABIT)
async def on_habit_mode(message: Message, state: FSMContext, user: dict) -> None:
    """Enter habit tracker mode."""
    await state.set_state(TrackerModes.habit_mode)

    stats = await db.get_habit_stats(user["id"])
    today = stats["today"]

    await message.answer(
        "🎯 <b>Odat Tracker</b>\n\n"
        f"Bugun bajarilgan odatlar: <b>{today}</b>\n"
        f"Bu hafta: <b>{stats['week']}</b>\n"
        f"Bu oy: <b>{stats['month']}</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "<b>Yangi odat qo'shing:</b>\n"
        "• Matn yozing: <code>30 daqiqa yugurdim</code>\n"
        "• Yoki ovozli xabar yuboring 🎤\n\n"
        "<i>Boshqa rejimga o'tish uchun pastdagi tugmalardan tanlang.</i>",
        parse_mode="HTML",
    )


@router.message(F.text == BTN_BUDGET)
async def on_budget_mode(message: Message, state: FSMContext, user: dict) -> None:
    """Enter budget tracker mode."""
    await state.set_state(TrackerModes.budget_mode)

    stats = await db.get_budget_stats(user["id"])
    currency = user.get("currency") or "UZS"
    today_bal = stats["today_income"] - stats["today_expense"]
    month_bal = stats["month_income"] - stats["month_expense"]

    await message.answer(
        "💰 <b>Budjet Tracker</b>\n\n"
        "<b>Bugun:</b>\n"
        f"  💰 Kirim: <b>{format_amount(stats['today_income'], currency)}</b>\n"
        f"  💸 Chiqim: <b>{format_amount(stats['today_expense'], currency)}</b>\n"
        f"  📊 Qoldiq: <b>{format_amount(today_bal, currency)}</b>\n\n"
        "<b>Bu oy:</b>\n"
        f"  📈 Qoldiq: <b>{format_amount(month_bal, currency)}</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "<b>Yangi yozuv qo'shing:</b>\n"
        "• <code>Taksiga 25 ming to'ladim</code>\n"
        "• <code>Maosh 3 mln so'm keldi</code>\n"
        "• Yoki ovozli xabar 🎤",
        parse_mode="HTML",
    )


@router.message(F.text == BTN_REPORTS)
async def on_reports_button(message: Message, state: FSMContext) -> None:
    """Delegate to reports handler."""
    await state.clear()
    from bot.handlers.reports import cmd_report
    await cmd_report(message)


# ═════════════════════ COMMAND SHORTCUTS ═════════════════════
@router.message(F.text == "/habits")
@router.message(Command("habits"))
async def cmd_habits(message: Message, user: dict) -> None:
    from bot.services.analytics_service import compute_streak
    stats = await db.get_habit_stats(user["id"])
    streak = await compute_streak(user["id"])
    await message.answer(
        "📊 <b>Odatlar xulosasi</b>\n\n"
        f"• Bugun: <b>{stats['today']}</b>\n"
        f"• Hafta: <b>{stats['week']}</b>\n"
        f"• Oy: <b>{stats['month']}</b>\n"
        f"• 🔥 Streak: <b>{streak}</b> kun\n\n"
        "Batafsil: /report",
        parse_mode="HTML",
    )


@router.message(F.text == "/budget")
@router.message(Command("budget"))
async def cmd_budget(message: Message, user: dict) -> None:
    stats = await db.get_budget_stats(user["id"])
    currency = user.get("currency") or "UZS"
    month_balance = stats["month_income"] - stats["month_expense"]
    emoji = "✅" if month_balance >= 0 else "⚠️"
    await message.answer(
        "💰 <b>Budjet xulosasi</b>\n\n"
        f"<b>Bugun:</b> {format_amount(stats['today_expense'], currency)} chiqim\n"
        f"<b>Bu oy:</b>\n"
        f"  💰 Kirim: <b>{format_amount(stats['month_income'], currency)}</b>\n"
        f"  💸 Chiqim: <b>{format_amount(stats['month_expense'], currency)}</b>\n"
        f"  {emoji} Qoldiq: <b>{format_amount(month_balance, currency)}</b>\n\n"
        "Batafsil: /report",
        parse_mode="HTML",
    )


# ═════════════════════ VOICE HANDLER ═════════════════════
@router.message(F.voice)
async def handle_voice(message: Message, state: FSMContext, user: dict) -> None:
    user_id = user["id"]

    if not await can_use_voice(user_id):
        await message.answer(
            "🎤 <b>Ovozli xabarlar — Premium funksiya</b>\n\n"
            "Premium olish uchun: /premium\n\n"
            "Matn ko'rinishida yozing.",
            parse_mode="HTML",
        )
        return

    allowed, count, limit = await check_daily_limit(user_id)
    if not allowed:
        await _send_limit_reached(message, count, limit)
        return

    thinking = await message.answer("🎤 Ovoz tahlil qilinmoqda...")
    bot = message.bot

    tmp_ogg = tempfile.NamedTemporaryFile(delete=False, suffix=".ogg", prefix=f"voice_{user_id}_")
    tmp_ogg.close()

    try:
        file = await bot.get_file(message.voice.file_id)
        await bot.download_file(file.file_path, tmp_ogg.name)
        transcription = await ai.transcribe_voice(tmp_ogg.name)

        if not transcription or len(transcription) < 2:
            try:
                await thinking.edit_text("🎤 Ovoz tushunilmadi. Matn yozing.")
            except Exception:
                await message.answer("🎤 Ovoz tushunilmadi.")
            return

        try:
            await thinking.edit_text(f"🎤 <i>Eshitdim:</i> {transcription[:200]}", parse_mode="HTML")
        except Exception:
            pass

        await db.log_metric("voice_call", user_id=user_id)
        await _process_intent(message, state, user, transcription)

    except AIServiceError:
        try:
            await thinking.edit_text("🎤 Ovoz tushunilmadi. Matn yozing.")
        except Exception:
            pass
    except Exception as e:
        logger.error("Voice error: %s", e, exc_info=True)
        try:
            await thinking.edit_text("⚠️ Ovozni qayta ishlashda xatolik.")
        except Exception:
            pass
    finally:
        try:
            if os.path.exists(tmp_ogg.name):
                os.remove(tmp_ogg.name)
        except OSError:
            pass


# ═════════════════════ TEXT HANDLER ═════════════════════
@router.message(F.text & ~F.text.startswith("/"))
async def handle_text(message: Message, state: FSMContext, user: dict) -> None:
    text = clean_text(message.text or "")
    if not text:
        return

    # Ignore known menu buttons that should already be handled
    if text in {BTN_HABIT, BTN_BUDGET, BTN_CABINET, BTN_REPORTS}:
        return

    user_id = user["id"]
    allowed, count, limit = await check_daily_limit(user_id)
    if not allowed:
        await _send_limit_reached(message, count, limit)
        return

    await _process_intent(message, state, user, text)


# ═════════════════════ CORE ═════════════════════
async def _process_intent(
    message: Message, state: FSMContext, user: dict, text: str
) -> None:
    """Parse text, apply context-mode bias, save to DB."""
    user_id = user["id"]
    user_currency = user.get("currency") or "UZS"
    mode = await state.get_state()

    try:
        result = await ai.parse_intent(text)
    except AIServiceError:
        await message.answer("⚠️ AI xizmatida muammo. Qayta urinib ko'ring.")
        return
    except Exception as e:
        logger.error("Intent parse failed: %s", e, exc_info=True)
        await message.answer("⚠️ Kutilmagan xatolik.")
        return

    intent: ParsedIntent = result.intent
    if result.used_ai:
        await db.log_metric("ai_call", user_id=user_id)

    # ── CONTEXT BIAS ──
    # If user is in habit_mode but AI said expense → nudge toward habit
    # If in budget_mode but AI said habit → nudge toward budget
    if mode == TrackerModes.habit_mode.state:
        if intent.type in ("BUDGET_EXPENSE", "BUDGET_INCOME"):
            # Low-confidence budget in habit mode → reinterpret
            if intent.confidence < 0.85:
                await message.answer(
                    "🎯 <b>Odat Tracker rejimida</b>siz, lekin bu xarajatga o'xshadi.\n\n"
                    "💰 Budjet qo'shish uchun pastdagi 💰 <b>Budjet Tracker</b> tugmasini bosing.\n"
                    "🎯 Yoki odatingizni aniqroq yozing.",
                    parse_mode="HTML",
                )
                return
    elif mode == TrackerModes.budget_mode.state:
        if intent.type == "HABIT_LOG":
            if intent.confidence < 0.85:
                await message.answer(
                    "💰 <b>Budjet Tracker rejimida</b>siz, lekin bu odatga o'xshadi.\n\n"
                    "🎯 Odat qo'shish uchun pastdagi 🎯 <b>Odat Tracker</b> tugmasini bosing.\n"
                    "💰 Yoki xarajatingizni aniqroq yozing.",
                    parse_mode="HTML",
                )
                return

    # ── UNKNOWN ──
    if intent.type == "UNKNOWN" or intent.confidence < 0.7:
        await message.answer(
            "🤔 <b>Tushunmadim.</b> Masalan:\n\n"
            "• <code>Bugun 30 daqiqa yugurdim</code>\n"
            "• <code>Nonvoydan 15 000 so'm non oldim</code>\n"
            "• <code>Taksiga 25 ming to'ladim</code>\n"
            "• <code>Maosh 3 mln so'm</code>",
            parse_mode="HTML",
        )
        return

    logged_date = normalize_date(intent.date, today_local())

    # ── HABIT ──
    if intent.type == "HABIT_LOG":
        habit_name = (intent.habit_name or "Odat").strip()[:200]
        duration = sanitize_duration(intent.duration)
        try:
            await db.add_habit_log(
                user_id=user_id,
                habit_name=habit_name,
                duration=duration,
                unit=intent.duration_unit,
                logged_date=logged_date,
                raw_text=text,
            )
        except Exception as e:
            logger.error("add_habit_log failed: %s", e)
            await message.answer("⚠️ Ma'lumotlar bazasida xatolik. 5 daqiqadan so'ng.")
            return

        dur_str = format_duration(duration, intent.duration_unit) if duration else ""
        date_note = "" if logged_date == today_local() else f" <i>({logged_date.isoformat()})</i>"
        msg = f"✅ <b>{habit_name}</b>"
        if dur_str and dur_str != "bajarildi":
            msg += f" — <b>{dur_str}</b>"
        msg += f" saqlandi!{date_note}"

        # Show streak if milestone
        from bot.services.analytics_service import compute_streak
        streak = await compute_streak(user_id)
        if streak > 0 and streak % 7 == 0:
            msg += f"\n\n🔥 <b>{streak} kun streak!</b> Ajoyib!"

        await message.answer(msg, parse_mode="HTML")
        return

    # ── BUDGET ──
    if intent.type in ("BUDGET_EXPENSE", "BUDGET_INCOME"):
        amount = sanitize_amount(intent.amount)
        if amount is None or amount == 0:
            await message.answer(
                "🤔 Summani tushunolmadim. Aniqroq yozing:\n"
                "<code>25 000 so'm</code> yoki <code>2.5 mln</code>",
                parse_mode="HTML",
            )
            return

        currency = (intent.currency or user_currency).upper()
        type_ = "expense" if intent.type == "BUDGET_EXPENSE" else "income"
        category = intent.category if type_ == "expense" else None

        try:
            await db.add_budget_log(
                user_id=user_id,
                type_=type_,
                category=category,
                amount=amount,
                currency=currency,
                note=intent.note,
                logged_date=logged_date,
                raw_text=text,
            )
        except Exception as e:
            logger.error("add_budget_log failed: %s", e)
            await message.answer("⚠️ Ma'lumotlar bazasida xatolik.")
            return

        date_note = "" if logged_date == today_local() else f" <i>({logged_date.isoformat()})</i>"
        if type_ == "income":
            msg = f"💰 <b>Kirim</b> — <b>{format_amount(amount, currency)}</b> saqlandi!{date_note}"
        else:
            cat_label = category_label(category)
            msg = f"💸 {cat_label} — <b>{format_amount(amount, currency)}</b> saqlandi!{date_note}"
        await message.answer(msg, parse_mode="HTML")
        return

    await message.answer("🤔 Tushunmadim. /help bosing.")


async def _send_limit_reached(message: Message, count: int, limit: int) -> None:
    await message.answer(
        f"🚦 <b>Kunlik limit tugadi</b> ({count}/{limit})\n\n"
        f"Bepul tarifda kuniga {limit} ta log.\n"
        "Cheksiz: /premium",
        parse_mode="HTML",
    )


@router.message(F.sticker | F.animation)
async def handle_sticker(message: Message) -> None:
    await message.answer(
        "😊 Yaxshi stiker! Lekin men odat/xarajatni faqat matn yoki ovoz orqali qabul qilaman."
    )
