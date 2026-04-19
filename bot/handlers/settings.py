"""Settings and reset handlers."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.keyboards.settings import (
    currency_keyboard,
    reset_confirm_keyboard,
    settings_main_keyboard,
)
from bot.services.db_service import db
from bot.services.subscription_service import get_subscription_status_text
from bot.utils.logger import logger

router = Router(name="settings")


async def _build_settings_text(user: dict) -> str:
    status = await get_subscription_status_text(user["id"])
    currency = user.get("currency") or "UZS"
    rem = "✅ Yoqilgan" if user.get("reminders_on", True) else "❌ O'chirilgan"
    return (
        "⚙️ <b>Sozlamalar</b>\n\n"
        f"💱 Valyuta: <b>{currency}</b>\n"
        f"🔔 Eslatmalar: <b>{rem}</b>\n"
        f"💎 Obuna: <b>{status}</b>\n\n"
        "O'zgartirish uchun tugma bosing:"
    )


@router.message(Command("settings"))
async def cmd_settings(message: Message) -> None:
    user = await db.get_or_create_user(message.from_user.id)
    await message.answer(
        await _build_settings_text(user),
        parse_mode="HTML",
        reply_markup=settings_main_keyboard(
            reminders_on=user.get("reminders_on", True),
            currency=user.get("currency") or "UZS",
        ),
    )


@router.callback_query(F.data == "settings:currency")
async def on_settings_currency(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        "💱 <b>Valyutani tanlang:</b>",
        parse_mode="HTML",
        reply_markup=currency_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("currency:"))
async def on_currency_set(callback: CallbackQuery, user: dict) -> None:
    code = (callback.data or "").split(":", 1)[1]
    if code not in {"UZS", "USD", "EUR", "RUB"}:
        await callback.answer("Noto'g'ri valyuta", show_alert=True)
        return

    await db.update_user(user["id"], {"currency": code})
    await callback.answer(f"✅ Valyuta {code} ga o'zgartirildi")
    # Refresh settings
    fresh = await db.get_or_create_user(user["id"])
    await callback.message.edit_text(
        await _build_settings_text(fresh),
        parse_mode="HTML",
        reply_markup=settings_main_keyboard(
            reminders_on=fresh.get("reminders_on", True),
            currency=fresh.get("currency") or "UZS",
        ),
    )


@router.callback_query(F.data == "settings:reminders")
async def on_toggle_reminders(callback: CallbackQuery, user: dict) -> None:
    new_val = not user.get("reminders_on", True)
    await db.update_user(user["id"], {"reminders_on": new_val})
    await callback.answer("✅ Yangilandi")
    fresh = await db.get_or_create_user(user["id"])
    await callback.message.edit_text(
        await _build_settings_text(fresh),
        parse_mode="HTML",
        reply_markup=settings_main_keyboard(
            reminders_on=fresh.get("reminders_on", True),
            currency=fresh.get("currency") or "UZS",
        ),
    )


@router.callback_query(F.data == "settings:subscription")
async def on_settings_subscription(callback: CallbackQuery, user: dict) -> None:
    status = await get_subscription_status_text(user["id"])
    sub = await db.get_subscription(user["id"])

    extra = ""
    if sub.get("tier") == "premium":
        extra = (
            f"\n📋 Plan: <b>{sub.get('plan_code', '—')}</b>\n"
            f"📅 Tugaydi: <b>{str(sub.get('expires_at', '—'))[:10]}</b>\n"
        )
    else:
        extra = "\n<i>Premium olish uchun /premium bosing.</i>"

    await callback.message.edit_text(
        f"💎 <b>Obuna holati</b>\n\n{status}{extra}",
        parse_mode="HTML",
        reply_markup=settings_main_keyboard(
            reminders_on=user.get("reminders_on", True),
            currency=user.get("currency") or "UZS",
        ),
    )
    await callback.answer()


@router.callback_query(F.data == "settings:back")
async def on_settings_back(callback: CallbackQuery, user: dict) -> None:
    fresh = await db.get_or_create_user(user["id"])
    await callback.message.edit_text(
        await _build_settings_text(fresh),
        parse_mode="HTML",
        reply_markup=settings_main_keyboard(
            reminders_on=fresh.get("reminders_on", True),
            currency=fresh.get("currency") or "UZS",
        ),
    )
    await callback.answer()


# ═════════════════════ RESET ═════════════════════
@router.message(Command("reset"))
async def cmd_reset(message: Message) -> None:
    await message.answer(
        "⚠️ <b>Diqqat!</b>\n\n"
        "Bu amal barcha ma'lumotlaringizni butunlay o'chiradi:\n"
        "  • Odatlar tarixi\n"
        "  • Budjet yozuvlari\n"
        "  • Obuna tarixi\n\n"
        "Bu amal qaytarib bo'lmaydi. Davom etamizmi?",
        parse_mode="HTML",
        reply_markup=reset_confirm_keyboard(),
    )


@router.callback_query(F.data == "settings:reset")
async def on_settings_reset(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        "⚠️ <b>Diqqat!</b>\n\n"
        "Bu amal barcha ma'lumotlaringizni butunlay o'chiradi:\n"
        "  • Odatlar tarixi\n"
        "  • Budjet yozuvlari\n"
        "  • Obuna tarixi\n\n"
        "Bu amal qaytarib bo'lmaydi. Davom etamizmi?",
        parse_mode="HTML",
        reply_markup=reset_confirm_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "reset:confirm")
async def on_reset_confirm(callback: CallbackQuery, user: dict) -> None:
    try:
        await db.delete_user_data(user["id"])
        await callback.message.edit_text(
            "✅ <b>Barcha ma'lumotlaringiz o'chirildi.</b>\n\n"
            "Qayta boshlash uchun /start bosing."
        , parse_mode="HTML")
    except Exception as e:
        logger.error("Reset failed for %s: %s", user["id"], e)
        await callback.message.edit_text("⚠️ O'chirishda xatolik yuz berdi.")
    await callback.answer()


@router.callback_query(F.data == "cancel")
async def on_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.answer("Bekor qilindi")
