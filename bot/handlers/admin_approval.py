"""Admin approval handlers — runs inside admin group only.

Flow:
  1. Bot forwards receipt with Approve/Reject buttons
  2. Admin clicks Approve → subscription activated + user notified
  3. Admin clicks Reject → reason menu → user notified with reason
"""
from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.config import config
from bot.keyboards.subscription import (
    admin_approval_keyboard,
    rejection_reasons_keyboard,
)
from bot.services.db_service import db
from bot.states.user_states import AdminStates
from bot.utils.decorators import admin_group_only
from bot.utils.formatters import format_amount, format_date, now_local
from bot.utils.logger import logger

router = Router(name="admin_approval")


# ═════════════════════ APPROVE ═════════════════════
@router.callback_query(F.data.startswith("approve:"))
@admin_group_only
async def on_approve(callback: CallbackQuery) -> None:
    request_id = int((callback.data or "0:0").split(":", 1)[1])
    admin_id = callback.from_user.id

    req = await db.get_payment_request(request_id)
    if req is None:
        await callback.answer("So'rov topilmadi", show_alert=True)
        return

    if req["status"] != "pending":
        await callback.answer(f"Bu so'rov allaqachon {req['status']}", show_alert=True)
        return

    plan = config.get_plan(req["plan_code"])
    if plan is None:
        await callback.answer("Plan topilmadi", show_alert=True)
        return

    user_id = req["user_id"]

    try:
        # Activate premium
        new_expiry = await db.activate_premium(
            user_id=user_id,
            plan_code=plan.code,
            duration_days=plan.duration_days,
            price_uzs=plan.price_uzs,
            payment_request_id=request_id,
            approved_by=admin_id,
        )
        await db.mark_payment_approved(request_id, admin_id)
    except Exception as e:
        logger.error("Approval failed for request %s: %s", request_id, e, exc_info=True)
        await callback.answer("⚠️ Xatolik yuz berdi", show_alert=True)
        return

    # Update admin group message — remove keyboard, add "APPROVED" stamp
    admin_name = callback.from_user.full_name or f"Admin {admin_id}"
    try:
        await callback.message.edit_caption(
            caption=(
                (callback.message.caption or "")
                + f"\n\n✅ <b>TASDIQLANDI</b>\n"
                f"👮 Admin: {admin_name}\n"
                f"📅 Tugaydi: {format_date(new_expiry.date())}"
            ),
            parse_mode="HTML",
            reply_markup=None,
        )
    except Exception as e:
        logger.warning("Failed to edit admin msg: %s", e)

    # Notify user
    try:
        await callback.bot.send_message(
            user_id,
            "🎉 <b>Premium obunangiz tasdiqlandi!</b>\n\n"
            f"📋 Plan: <b>{plan.name_uz}</b>\n"
            f"💵 To'langan: <b>{format_amount(plan.price_uzs, 'UZS')}</b>\n"
            f"📅 Tugaydi: <b>{format_date(new_expiry.date())}</b>\n\n"
            "Endi barcha Premium imkoniyatlardan foydalanishingiz mumkin:\n"
            "  🎤 Ovozli xabarlar\n"
            "  📄 PDF hisobotlar\n"
            "  ♾ Cheksiz loglar\n"
            "  📊 Kengaytirilgan statistika\n\n"
            "Rahmat! 🙏",
            parse_mode="HTML",
        )
    except Exception as e:
        logger.error("Failed to notify user %s: %s", user_id, e)

    await callback.answer("✅ Tasdiqlandi va userga xabar yuborildi", show_alert=False)


# ═════════════════════ REJECT FLOW ═════════════════════
@router.callback_query(F.data.startswith("reject:"))
@admin_group_only
async def on_reject(callback: CallbackQuery) -> None:
    request_id = int((callback.data or "0:0").split(":", 1)[1])
    req = await db.get_payment_request(request_id)
    if req is None or req["status"] != "pending":
        await callback.answer("So'rov mavjud emas yoki allaqachon hal qilingan", show_alert=True)
        return

    try:
        await callback.message.edit_reply_markup(
            reply_markup=rejection_reasons_keyboard(request_id)
        )
    except Exception:
        pass
    await callback.answer()


@router.callback_query(F.data.startswith("back_approval:"))
@admin_group_only
async def on_back_approval(callback: CallbackQuery) -> None:
    request_id = int((callback.data or "0:0").split(":", 1)[1])
    try:
        await callback.message.edit_reply_markup(
            reply_markup=admin_approval_keyboard(request_id)
        )
    except Exception:
        pass
    await callback.answer()


REASON_LABELS = {
    "unclear": "Chek ko'rinmadi / rasm sifati past",
    "wrong_amount": "To'lov summasi noto'g'ri",
    "fake": "Chek soxta deb topildi",
}


@router.callback_query(F.data.startswith("reject_reason:"))
@admin_group_only
async def on_reject_reason(callback: CallbackQuery, state: FSMContext) -> None:
    parts = (callback.data or "").split(":")
    if len(parts) < 3:
        await callback.answer("Xatolik", show_alert=True)
        return

    request_id = int(parts[1])
    reason_code = parts[2]

    if reason_code == "custom":
        await state.set_state(AdminStates.waiting_rejection_reason)
        await state.update_data(request_id=request_id, admin_msg_id=callback.message.message_id)
        await callback.message.reply(
            "✍️ Rad etish sababini yozing (reply qiling bu xabarga):\n"
            "<i>Max 300 belgi.</i>",
            parse_mode="HTML",
        )
        await callback.answer()
        return

    reason_text = REASON_LABELS.get(reason_code, "Rad etildi")
    await _finalize_rejection(callback.bot, callback.message, request_id, callback.from_user.id, reason_text)
    await callback.answer("❌ Rad etildi")


@router.message(AdminStates.waiting_rejection_reason, F.text)
async def on_custom_rejection_reason(message: Message, state: FSMContext) -> None:
    # Only in admin group
    if message.chat.id != config.admin_group_id:
        return
    if message.from_user.id not in config.admin_ids:
        return

    data = await state.get_data()
    request_id = data.get("request_id")
    if not request_id:
        await state.clear()
        return

    reason = (message.text or "").strip()[:300]
    if not reason:
        await message.reply("Sabab bo'sh bo'lishi mumkin emas")
        return

    await _finalize_rejection(message.bot, message, request_id, message.from_user.id, reason, find_msg=True)
    await state.clear()
    await message.reply("✅ Rad etildi va userga xabar yuborildi")


async def _finalize_rejection(
    bot,
    source_msg,
    request_id: int,
    admin_id: int,
    reason: str,
    find_msg: bool = False,
) -> None:
    req = await db.get_payment_request(request_id)
    if req is None or req["status"] != "pending":
        return

    try:
        await db.mark_payment_rejected(request_id, admin_id, reason)
    except Exception as e:
        logger.error("mark_rejected failed: %s", e)
        return

    # Update admin group message
    admin_chat_id = req.get("admin_chat_id")
    admin_msg_id = req.get("admin_message_id")
    if admin_chat_id and admin_msg_id:
        try:
            # Fetch and edit caption
            await bot.edit_message_caption(
                chat_id=admin_chat_id,
                message_id=admin_msg_id,
                caption=(
                    "❌ <b>RAD ETILDI</b>\n\n"
                    f"🆔 Request: <code>#{request_id}</code>\n"
                    f"👮 Admin ID: <code>{admin_id}</code>\n"
                    f"📝 Sabab: {reason}"
                ),
                parse_mode="HTML",
                reply_markup=None,
            )
        except Exception as e:
            logger.debug("Failed to edit rejection caption: %s", e)

    # Notify user
    user_id = req["user_id"]
    plan = config.get_plan(req["plan_code"])
    plan_name = plan.name_uz if plan else req["plan_code"]
    try:
        await bot.send_message(
            user_id,
            "❌ <b>Afsuski, to'lovingiz rad etildi.</b>\n\n"
            f"📋 Plan: <b>{plan_name}</b>\n"
            f"📝 <b>Sabab:</b> {reason}\n\n"
            "Qayta urinib ko'rish uchun: /premium\n\n"
            "<i>Savollar bo'lsa, administrator bilan bog'laning.</i>",
            parse_mode="HTML",
        )
    except Exception as e:
        logger.error("Failed to notify user of rejection %s: %s", user_id, e)


# ═════════════════════ USER INFO ═════════════════════
@router.callback_query(F.data.startswith("user_info:"))
@admin_group_only
async def on_user_info(callback: CallbackQuery) -> None:
    request_id = int((callback.data or "0:0").split(":", 1)[1])
    req = await db.get_payment_request(request_id)
    if req is None:
        await callback.answer("Topilmadi", show_alert=True)
        return

    user_id = req["user_id"]
    user = await db.get_user_info(user_id)
    sub = await db.get_subscription(user_id)
    habit_stats = await db.get_habit_stats(user_id)
    budget_stats = await db.get_budget_stats(user_id)

    if user is None:
        await callback.answer("User topilmadi", show_alert=True)
        return

    text = (
        f"👤 <b>User ma'lumotlari</b>\n\n"
        f"🆔 ID: <code>{user_id}</code>\n"
        f"📛 Ism: {user.get('full_name') or '—'}\n"
        f"🔗 Username: @{user.get('username') or '—'}\n"
        f"📅 Ro'yxatdan o'tgan: {str(user.get('created_at', ''))[:10]}\n"
        f"⏱ Oxirgi faollik: {str(user.get('last_active_at', ''))[:16]}\n"
        f"💎 Obuna: {sub.get('tier', 'free')}\n\n"
        f"<b>Faollik:</b>\n"
        f"  • Odatlar (oy): {habit_stats['month']} ta\n"
        f"  • Bugungi chiqim: {budget_stats['today_expense']:,.0f}\n"
        f"  • Oylik chiqim: {budget_stats['month_expense']:,.0f}\n"
    )
    await callback.answer(text, show_alert=True)
