"""Admin panel: /admin command with stats, broadcast, user lookup."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.config import config
from bot.keyboards.admin import (
    admin_main_keyboard,
    back_to_admin_keyboard,
    broadcast_confirm_keyboard,
    user_action_keyboard,
)
from bot.services.db_service import db
from bot.states.user_states import AdminStates
from bot.utils.decorators import admin_only
from bot.utils.formatters import format_amount, format_date, today_local
from bot.utils.logger import logger

router = Router(name="admin_panel")


async def _build_stats_text() -> str:
    stats = await db.admin_stats()
    return (
        "📊 <b>Admin Panel — Statistika</b>\n\n"
        f"👥 <b>Foydalanuvchilar</b>\n"
        f"  • Jami: <b>{stats['total_users']:,}</b>\n"
        f"  • Bugun faol (DAU): <b>{stats['dau']:,}</b>\n"
        f"  • Haftalik faol (WAU): <b>{stats['wau']:,}</b>\n"
        f"  • Premium: <b>{stats['premium_active']:,}</b>\n\n"
        f"📝 <b>Bugungi loglar</b>\n"
        f"  • Odatlar: <b>{stats['habits_today']:,}</b>\n"
        f"  • Budjet yozuvlari: <b>{stats['budget_today']:,}</b>\n\n"
        f"💰 <b>Daromad</b>\n"
        f"  • Oylik: <b>{format_amount(stats['month_revenue_uzs'], 'UZS')}</b>\n"
        f"  • Jami: <b>{format_amount(stats['total_revenue_uzs'], 'UZS')}</b>\n\n"
        f"⏳ <b>Kutilayotgan to'lovlar:</b> <b>{stats['pending_requests']}</b>\n\n"
        f"<i>Yangilangan: {datetime.now().strftime('%H:%M:%S')}</i>"
    )


@router.message(Command("admin"))
@admin_only
async def cmd_admin(message: Message) -> None:
    pending = await db.count_pending_requests()
    text = await _build_stats_text()
    await message.answer(
        text,
        parse_mode="HTML",
        reply_markup=admin_main_keyboard(pending_count=pending),
    )


@router.callback_query(F.data == "admin:refresh")
@admin_only
async def on_admin_refresh(callback: CallbackQuery) -> None:
    pending = await db.count_pending_requests()
    text = await _build_stats_text()
    try:
        await callback.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=admin_main_keyboard(pending_count=pending),
        )
    except TelegramAPIError:
        pass
    await callback.answer("🔄 Yangilandi")


@router.callback_query(F.data == "admin:stats")
@admin_only
async def on_admin_stats(callback: CallbackQuery) -> None:
    pending = await db.count_pending_requests()
    text = await _build_stats_text()
    try:
        await callback.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=admin_main_keyboard(pending_count=pending),
        )
    except TelegramAPIError:
        pass
    await callback.answer()


# ═════════════════════ PENDING REQUESTS ═════════════════════
@router.callback_query(F.data == "admin:pending")
@admin_only
async def on_admin_pending(callback: CallbackQuery) -> None:
    requests = await db.get_pending_payment_requests(limit=10)
    if not requests:
        await callback.message.edit_text(
            "✅ <b>Kutilayotgan to'lovlar yo'q</b>\n\n"
            "Hamma so'rovlar ko'rib chiqilgan.",
            parse_mode="HTML",
            reply_markup=back_to_admin_keyboard(),
        )
        await callback.answer()
        return

    lines = ["⏳ <b>Kutilayotgan to'lovlar</b>\n"]
    for req in requests[:10]:
        user_data = req.get("users") or {}
        name = user_data.get("full_name") or f"User {req['user_id']}"
        username = user_data.get("username")
        name_link = f"{name} (@{username})" if username else name
        submitted = str(req.get("submitted_at", ""))[:16].replace("T", " ")
        plan = config.get_plan(req["plan_code"])
        plan_name = plan.name_uz if plan else req["plan_code"]
        lines.append(
            f"• #{req['id']} — {name_link}\n"
            f"  {plan_name} ({format_amount(req['expected_amount'], 'UZS')})\n"
            f"  📅 {submitted}"
        )

    lines.append(
        f"\n<i>Jami: {len(requests)} ta. To'lovlar admin guruhida ko'rish mumkin.</i>"
    )
    await callback.message.edit_text(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=back_to_admin_keyboard(),
    )
    await callback.answer()


# ═════════════════════ FIND USER ═════════════════════
@router.callback_query(F.data == "admin:find_user")
@admin_only
async def on_admin_find_user(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminStates.waiting_user_id_lookup)
    await callback.message.edit_text(
        "🔍 <b>User qidirish</b>\n\n"
        "Telegram user ID ni yuboring (raqamlar):\n"
        "<i>Misol: 123456789</i>",
        parse_mode="HTML",
        reply_markup=back_to_admin_keyboard(),
    )
    await callback.answer()


@router.message(AdminStates.waiting_user_id_lookup, F.text)
async def on_user_lookup_text(message: Message, state: FSMContext) -> None:
    if message.from_user.id not in config.admin_ids:
        return

    text = (message.text or "").strip()
    if not text.isdigit():
        await message.answer("❌ Faqat raqamli ID kiriting")
        return

    user_id = int(text)
    user = await db.get_user_info(user_id)
    if user is None:
        await message.answer("👤 User topilmadi")
        return

    sub = await db.get_subscription(user_id)
    habit_stats = await db.get_habit_stats(user_id)
    budget_stats = await db.get_budget_stats(user_id)

    info = (
        f"👤 <b>User #{user_id}</b>\n\n"
        f"📛 Ism: {user.get('full_name') or '—'}\n"
        f"🔗 Username: @{user.get('username') or '—'}\n"
        f"💱 Valyuta: {user.get('currency', 'UZS')}\n"
        f"🔔 Eslatmalar: {'✅' if user.get('reminders_on') else '❌'}\n"
        f"🚫 Bloklangan: {'Ha' if user.get('is_banned') else 'Yoq'}\n"
        f"📅 Ro'yxat: {str(user.get('created_at', ''))[:10]}\n"
        f"⏱ Oxirgi faollik: {str(user.get('last_active_at', ''))[:16].replace('T', ' ')}\n\n"
        f"💎 Obuna: <b>{sub.get('tier', 'free')}</b>\n"
        f"📅 Tugaydi: {str(sub.get('expires_at') or '—')[:10]}\n\n"
        f"<b>Faollik:</b>\n"
        f"  • Odatlar (bu oy): {habit_stats['month']}\n"
        f"  • Chiqim (bu oy): {format_amount(budget_stats['month_expense'], user.get('currency', 'UZS'))}\n"
        f"  • Kirim (bu oy): {format_amount(budget_stats['month_income'], user.get('currency', 'UZS'))}"
    )
    await state.clear()
    await message.answer(
        info,
        parse_mode="HTML",
        reply_markup=user_action_keyboard(user_id, is_banned=user.get("is_banned", False)),
    )


@router.callback_query(F.data.startswith("admin_user:"))
@admin_only
async def on_admin_user_action(callback: CallbackQuery) -> None:
    parts = (callback.data or "").split(":")
    if len(parts) < 3:
        await callback.answer("Xato", show_alert=True)
        return
    action = parts[1]
    user_id = int(parts[2])

    if action == "ban":
        await db.ban_user(user_id, banned=True)
        await callback.answer("🚫 Bloklandi", show_alert=False)
    elif action == "unban":
        await db.ban_user(user_id, banned=False)
        await callback.answer("✅ Bloklash olib tashlandi", show_alert=False)
    elif action == "grant":
        # Grant 30 days premium manually
        try:
            new_expiry = await db.activate_premium(
                user_id=user_id,
                plan_code="admin_gift",
                duration_days=30,
                price_uzs=0,
                payment_request_id=0,
                approved_by=callback.from_user.id,
            )
            await callback.answer(f"✅ 30 kun Premium berildi ({new_expiry.date()})", show_alert=True)
            try:
                await callback.bot.send_message(
                    user_id,
                    "🎁 <b>Sizga administrator tomonidan 30 kunlik Premium berildi!</b>\n\n"
                    f"📅 Tugaydi: <b>{format_date(new_expiry.date())}</b>\n\n"
                    "Barcha Premium imkoniyatlardan foydalaning! 💎",
                    parse_mode="HTML",
                )
            except Exception:
                pass
        except Exception as e:
            logger.error("Grant premium failed: %s", e)
            await callback.answer("⚠️ Xatolik", show_alert=True)


# ═════════════════════ BROADCAST ═════════════════════
@router.callback_query(F.data == "admin:broadcast")
@admin_only
async def on_admin_broadcast(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminStates.waiting_broadcast_text)
    await callback.message.edit_text(
        "📢 <b>Broadcast yuborish</b>\n\n"
        "Yubormoqchi bo'lgan matnni yozing.\n"
        "HTML taglari qabul qilinadi (<code>&lt;b&gt;</code>, <code>&lt;i&gt;</code>, ...).\n\n"
        "Bekor qilish uchun /cancel",
        parse_mode="HTML",
        reply_markup=back_to_admin_keyboard(),
    )
    await callback.answer()


@router.message(AdminStates.waiting_broadcast_text, F.text)
async def on_broadcast_text(message: Message, state: FSMContext) -> None:
    if message.from_user.id not in config.admin_ids:
        return
    text = (message.text or "").strip()
    if text in {"/cancel", "cancel"}:
        await state.clear()
        await message.answer("❌ Bekor qilindi")
        return

    await state.update_data(broadcast_text=text)
    await state.set_state(AdminStates.confirming_broadcast)

    user_count = len(await db.get_all_active_user_ids())
    preview = (
        "📢 <b>Broadcast — oldindan ko'rish</b>\n\n"
        "════════════════════\n"
        f"{text}\n"
        "════════════════════\n\n"
        f"👥 Taxminan <b>{user_count:,}</b> foydalanuvchiga yuboriladi.\n\n"
        "Yuborishni tasdiqlaysizmi?"
    )
    await message.answer(
        preview,
        parse_mode="HTML",
        reply_markup=broadcast_confirm_keyboard(),
    )


@router.callback_query(F.data == "broadcast:cancel")
@admin_only
async def on_broadcast_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text(
        "❌ Broadcast bekor qilindi.",
        reply_markup=back_to_admin_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "broadcast:send")
@admin_only
async def on_broadcast_send(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    text = data.get("broadcast_text", "")
    await state.clear()

    if not text:
        await callback.answer("Matn yo'q", show_alert=True)
        return

    await callback.message.edit_text(
        "📤 <b>Yuborilmoqda...</b>",
        parse_mode="HTML",
    )
    await callback.answer()

    user_ids = await db.get_all_active_user_ids()
    sent = failed = 0
    bot = callback.bot

    for uid in user_ids:
        try:
            await bot.send_message(uid, text, parse_mode="HTML")
            sent += 1
            # Rate limit: ~25 msg/sec
            await asyncio.sleep(0.04)
        except TelegramAPIError:
            failed += 1
        except Exception as e:
            failed += 1
            logger.debug("Broadcast err for %s: %s", uid, e)

    await db.log_broadcast(
        admin_id=callback.from_user.id,
        text=text,
        sent=sent,
        failed=failed,
    )

    await callback.message.edit_text(
        f"✅ <b>Broadcast yakunlandi</b>\n\n"
        f"📤 Yuborildi: <b>{sent:,}</b>\n"
        f"❌ Xato: <b>{failed:,}</b>\n"
        f"📊 Jami: <b>{sent + failed:,}</b>",
        parse_mode="HTML",
        reply_markup=back_to_admin_keyboard(),
    )


# ═════════════════════ REVENUE ═════════════════════
@router.callback_query(F.data == "admin:revenue")
@admin_only
async def on_admin_revenue(callback: CallbackQuery) -> None:
    stats = await db.admin_stats()
    text = (
        "💰 <b>Daromad hisoboti</b>\n\n"
        f"📅 <b>Bu oy:</b> {format_amount(stats['month_revenue_uzs'], 'UZS')}\n"
        f"📊 <b>Jami (barcha vaqt):</b> {format_amount(stats['total_revenue_uzs'], 'UZS')}\n\n"
        f"💎 <b>Hozir Premium:</b> {stats['premium_active']:,} user\n\n"
        f"<i>Faqat tasdiqlangan to'lovlar hisoblanadi.</i>"
    )
    try:
        await callback.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=back_to_admin_keyboard(),
        )
    except TelegramAPIError:
        pass
    await callback.answer()


# Cancel generic command for admin flows
@router.message(Command("cancel"))
async def cmd_cancel_admin(message: Message, state: FSMContext) -> None:
    current = await state.get_state()
    if current and current.startswith("AdminStates"):
        await state.clear()
        await message.answer("❌ Bekor qilindi")
