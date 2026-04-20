"""Main message handler: text + voice parsing with context modes.

UPDATED: Multi-intent parsing + Gemini fallback.

Context modes (activated via main menu buttons):
  • habit_mode  — AI biased toward habit logs
  • budget_mode — AI biased toward budget logs
  • no state    — auto-detect (fallback)
"""
from __future__ import annotations

import os
import tempfile
from typing import List

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
        "• Bir nechta odat: <code>yugurdim. kitob o'qidim. dush qildim</code>\n"
        "• Yoki ovozli xabar yuboring 🎤\n\n"
        "<i>Boshqa rejimga o'tish uchun pastdagi tugmalardan tanlang.</i>",
        parse_mode="HTML",
    )


@router.message(F.text == BTN_BUDGET)
async def on_budget_mode(message: Message, state: FSMContext, user: dict) -> None:
    await state.set_state(TrackerModes.budget_mode)

    stats = await db.get_budget_stats(user["id"])
    currency = user.get("currency") or "UZS"
    today_bal = stats["today_income"] - stats["today_expense"]
    month_bal = stats["month_income"] - stats["month_expense"]

    await message.answer(
        "💰 <b>Budjet Tracker</b>\n\n"
        f"Bugun:\n"
        f"  💰 Kirim: <b>{format_amount(stats['today_income'], currency)}</b>\n"
        f"  💸 Chiqim: <b>{format_amount(stats['today_expense'], currency)}</b>\n"
        f"  📊 Qoldiq: <b>{format_amount(today_bal, currency)}</b>\n\n"
        f"Bu oy:\n"
        f"  📈 Qoldiq: <b>{format_amount(month_bal, currency)}</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "<b>Yangi yozuv qo'shing:</b>\n"
        "• Taksiga 25 ming to'ladim\n"
        "• Maosh 3 mln so'm\n"
        "• Yoki ovozli xabar yuboring 🎤",
        parse_mode="HTML",
    )


# ═════════════════════ VOICE HANDLER ═════════════════════
@router.message(F.voice)
async def handle_voice(message: Message, state: FSMContext, user: dict) -> None:
    user_id = user["id"]

    is_premium = await can_use_voice(user_id)
    if not is_premium:
        await message.answer(
            "🎤 <b>Ovozli xabarlar — Premium funksiya</b>\n\n"
            "Premium olish uchun: /premium\n"
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
        await _process_intents(message, state, user, transcription)

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

    # Skip menu buttons — ular alohida handlerlar tomonidan qayta ishlanadi
    if text in {BTN_HABIT, BTN_BUDGET, BTN_CABINET, BTN_REPORTS}:
        return

    user_id = user["id"]
    allowed, count, limit = await check_daily_limit(user_id)
    if not allowed:
        await _send_limit_reached(message, count, limit)
        return

    await _process_intents(message, state, user, text)


# ═════════════════════ CORE ═════════════════════
async def _process_intents(
    message: Message, state: FSMContext, user: dict, text: str
) -> None:
    """Parse text, save ALL detected intents (multi-intent support)."""
    user_id = user["id"]
    user_currency = user.get("currency") or "UZS"

    try:
        result = await ai.parse_intent(text)
    except AIServiceError:
        await message.answer(
            "⚠️ AI xizmatida vaqtincha muammo. Bir ozdan keyin urinib ko'ring."
        )
        return
    except Exception as e:
        logger.error("Intent parse failed: %s", e, exc_info=True)
        await message.answer("⚠️ Kutilmagan xatolik.")
        return

    if result.used_ai:
        await db.log_metric("ai_call", user_id=user_id)

    intents: List[ParsedIntent] = result.intents

    # Filter out UNKNOWN/low-confidence intents
    valid_intents = [i for i in intents if i.type != "UNKNOWN" and i.confidence >= 0.5]

    if not valid_intents:
        await message.answer(
            "🤔 <b>Tushunmadim.</b> Masalan:\n\n"
            "• <code>Bugun 30 daqiqa yugurdim</code>\n"
            "• <code>Nonvoydan 15 000 so'm non oldim</code>\n"
            "• <code>Taksiga 25 ming to'ladim</code>\n"
            "• <code>Maosh 3 mln so'm</code>\n"
            "• <code>Yugurdim. Kitob o'qidim. Dush qildim</code>",
            parse_mode="HTML",
        )
        return

    # Process each intent and collect results
    saved_habits: List[str] = []
    saved_expenses: List[str] = []
    saved_incomes: List[str] = []
    errors: List[str] = []

    for intent in valid_intents:
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
                dur_str = format_duration(duration, intent.duration_unit) if duration else ""
                if dur_str and dur_str != "bajarildi":
                    saved_habits.append(f"<b>{habit_name}</b> — {dur_str}")
                else:
                    saved_habits.append(f"<b>{habit_name}</b>")
            except Exception as e:
                logger.error("add_habit_log failed: %s", e)
                errors.append(habit_name)
            continue

        # ── BUDGET ──
        if intent.type in ("BUDGET_EXPENSE", "BUDGET_INCOME"):
            amount = sanitize_amount(intent.amount)
            if amount is None or amount == 0:
                continue

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
                amount_str = format_amount(amount, currency)
                if type_ == "income":
                    saved_incomes.append(f"<b>{amount_str}</b>")
                else:
                    cat_label = category_label(category)
                    saved_expenses.append(f"{cat_label} — <b>{amount_str}</b>")
            except Exception as e:
                logger.error("add_budget_log failed: %s", e)
                errors.append(f"xarajat {amount}")
            continue

    # Build combined response message
    await _send_summary(
        message, saved_habits, saved_expenses, saved_incomes, errors, user_id
    )


async def _send_summary(
    message: Message,
    habits: List[str],
    expenses: List[str],
    incomes: List[str],
    errors: List[str],
    user_id: int,
) -> None:
    """Build a clear summary of everything that was saved."""
    total = len(habits) + len(expenses) + len(incomes)

    if total == 0:
        await message.answer(
            "⚠️ Saqlash mumkin bo'lmadi. Qayta urinib ko'ring."
        )
        return

    # Check streak once (works for any habit save)
    streak_line = ""
    if habits:
        from bot.services.analytics_service import compute_streak
        try:
            streak = await compute_streak(user_id)
            if streak > 0 and streak % 7 == 0:
                streak_line = f"\n\n🔥 <b>{streak} kun streak!</b> Ajoyib!"
        except Exception:
            pass

    # Single-item: keep it concise
    if total == 1 and not errors:
        if habits:
            msg = f"✅ {habits[0]} saqlandi!"
        elif incomes:
            msg = f"💰 Kirim — {incomes[0]} saqlandi!"
        elif expenses:
            msg = f"💸 {expenses[0]} saqlandi!"
        else:
            msg = "✅ Saqlandi!"

        await message.answer(msg + streak_line, parse_mode="HTML")
        return

    # Multi-item summary
    lines = [f"✅ <b>{total} ta yozuv saqlandi:</b>\n"]

    if habits:
        lines.append("🎯 <b>Odatlar:</b>")
        for h in habits:
            lines.append(f"  • {h}")
        lines.append("")

    if expenses:
        lines.append("💸 <b>Chiqimlar:</b>")
        for e in expenses:
            lines.append(f"  • {e}")
        lines.append("")

    if incomes:
        lines.append("💰 <b>Kirimlar:</b>")
        for i in incomes:
            lines.append(f"  • {i}")
        lines.append("")

    if errors:
        lines.append(f"⚠️ <i>{len(errors)} ta yozuvda xatolik.</i>")

    final = "\n".join(lines).strip() + streak_line
    await message.answer(final, parse_mode="HTML")


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
