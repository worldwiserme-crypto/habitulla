"""User-side subscription flow: /premium → plan → upload receipt → wait for admin."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.config import config
from bot.keyboards.common import main_reply_keyboard
from bot.keyboards.subscription import (
    admin_approval_keyboard,
    plan_selection_keyboard,
    upload_receipt_keyboard,
)
from bot.services.db_service import db
from bot.services.subscription_service import (
    get_subscription_status_text,
    is_premium,
)
from bot.states.user_states import SubscriptionStates
from bot.utils.formatters import format_amount
from bot.utils.logger import logger

router = Router(name="subscription")


PREMIUM_INTRO = """💎 <b>Premium obuna</b>

<b>Premium nima beradi?</b>
  ✅ Cheksiz log qo'shish (bepul — kuniga 10 ta)
  ✅ Ovozli xabarlar 🎤
  ✅ PDF + grafikli hisobotlar
  ✅ Istalgan sana oralig'ida hisobot
  ✅ Kengaytirilgan statistika va streak
  ✅ AI-maslahat va tahlillar
  ✅ Budjet limit ogohlantirishlari
  ✅ Reklamasiz

<b>Hozirgi holat:</b> {status}

Planni tanlang:"""


@router.message(Command("premium"))
async def cmd_premium(message: Message, state: FSMContext = None) -> None:
    user_id = message.from_user.id

    # Check pending request
    if await db.user_has_pending_request(user_id):
        await message.answer(
            "⏳ <b>Sizning oldingi to'lovingiz hali tekshirilmoqda.</b>\n\n"
            "Administrator javob berishini kuting (odatda 1-24 soat).\n"
            "Agar shoshilinch bo'lsa, admin bilan bog'laning.",
            parse_mode="HTML",
        )
        return

    status = await get_subscription_status_text(user_id)
    if state:
        await state.set_state(SubscriptionStates.waiting_plan_selection)

    await message.answer(
        PREMIUM_INTRO.format(status=status),
        parse_mode="HTML",
        reply_markup=plan_selection_keyboard(),
    )


@router.callback_query(F.data.startswith("plan:"))
async def on_plan_selected(callback: CallbackQuery, state: FSMContext) -> None:
    plan_code = (callback.data or "").split(":", 1)[1]
    plan = config.get_plan(plan_code)
    if plan is None:
        await callback.answer("Plan topilmadi", show_alert=True)
        return

    await state.update_data(plan_code=plan_code)
    await state.set_state(SubscriptionStates.waiting_receipt)

    payment_text = (
        f"💎 <b>Tanlangan plan:</b> {plan.name_uz}\n"
        f"💰 <b>To'lov summasi:</b> {format_amount(plan.price_uzs, 'UZS')}\n\n"
        "<b>To'lov usullari:</b>\n\n"
        f"💳 <b>Karta raqami:</b>\n<code>{config.payment_card_number}</code>\n"
        f"👤 <b>Egasi:</b> {config.payment_card_holder}\n\n"
    )

    if config.payment_click_phone:
        payment_text += f"📱 <b>Click:</b> <code>{config.payment_click_phone}</code>\n"
    if config.payment_payme_phone:
        payment_text += f"📱 <b>Payme:</b> <code>{config.payment_payme_phone}</code>\n"

    payment_text += (
        "\n<b>Keyingi qadamlar:</b>\n"
        "1️⃣ Yuqoridagi rekvizitga to'lovni amalga oshiring\n"
        "2️⃣ Chek <b>rasm</b> yoki <b>PDF</b> shaklida shu yerga yuboring\n"
        "3️⃣ Administrator tasdiqlashini kuting (odatda 1-24 soat)\n\n"
        "⬇️ Chek yuborishni kutyapman..."
    )

    await callback.message.edit_text(
        payment_text,
        parse_mode="HTML",
        reply_markup=upload_receipt_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "back_to_plans")
async def on_back_to_plans(callback: CallbackQuery, state: FSMContext, user: dict) -> None:
    await state.set_state(SubscriptionStates.waiting_plan_selection)
    status = await get_subscription_status_text(user["id"])
    await callback.message.edit_text(
        PREMIUM_INTRO.format(status=status),
        parse_mode="HTML",
        reply_markup=plan_selection_keyboard(),
    )
    await callback.answer()


@router.message(SubscriptionStates.waiting_receipt, F.photo)
async def on_receipt_photo(message: Message, state: FSMContext, user: dict) -> None:
    await _process_receipt(
        message=message,
        state=state,
        user=user,
        file_id=message.photo[-1].file_id,
        file_type="photo",
    )


@router.message(SubscriptionStates.waiting_receipt, F.document)
async def on_receipt_document(message: Message, state: FSMContext, user: dict) -> None:
    doc = message.document
    # Only accept PDFs and images
    mime = (doc.mime_type or "").lower()
    if not (mime == "application/pdf" or mime.startswith("image/")):
        await message.answer(
            "📄 Faqat PDF yoki rasm qabul qilinadi.\n"
            "Iltimos, chekning rasm yoki PDF nusxasini yuboring."
        )
        return

    if doc.file_size and doc.file_size > 10 * 1024 * 1024:
        await message.answer("📦 Fayl juda katta (maks. 10 MB).")
        return

    await _process_receipt(
        message=message,
        state=state,
        user=user,
        file_id=doc.file_id,
        file_type="document",
    )


@router.message(SubscriptionStates.waiting_receipt)
async def on_wrong_receipt_type(message: Message) -> None:
    await message.answer(
        "📎 Iltimos, chek <b>rasm</b> yoki <b>PDF</b> shaklida yuboring.\n"
        "Matn yoki ovozli xabar qabul qilinmaydi.",
        parse_mode="HTML",
    )


async def _process_receipt(
    message: Message,
    state: FSMContext,
    user: dict,
    file_id: str,
    file_type: str,
) -> None:
    data = await state.get_data()
    plan_code = data.get("plan_code")
    plan = config.get_plan(plan_code) if plan_code else None
    if plan is None:
        await message.answer("⚠️ Planni qayta tanlang: /premium")
        await state.clear()
        return

    if config.admin_group_id == 0:
        await message.answer(
            "⚠️ Administratorga yuborishda xatolik. Admin bilan bog'laning."
        )
        logger.error("ADMIN_GROUP_ID not configured!")
        await state.clear()
        return

    # Create payment request
    try:
        request_id = await db.create_payment_request(
            user_id=user["id"],
            plan_code=plan_code,
            expected_amount=plan.price_uzs,
            receipt_file_id=file_id,
            receipt_file_type=file_type,
        )
    except Exception as e:
        logger.error("create_payment_request failed: %s", e)
        await message.answer("⚠️ Ma'lumotlar bazasida xatolik. Keyinroq urining.")
        await state.clear()
        return

    # Forward to admin group
    username_link = f"@{message.from_user.username}" if message.from_user.username else "—"
    caption = (
        "💰 <b>YANGI TO'LOV SO'ROVI</b>\n\n"
        f"🆔 Request: <code>#{request_id}</code>\n"
        f"👤 User: <code>{user['id']}</code>\n"
        f"📛 Ism: {user.get('full_name') or '—'}\n"
        f"🔗 Username: {username_link}\n"
        f"📋 Plan: <b>{plan.name_uz}</b>\n"
        f"💵 Kutilgan summa: <b>{format_amount(plan.price_uzs, 'UZS')}</b>\n\n"
        "⬇️ Chek quyida. Tasdiqlash yoki rad etish uchun tugma bosing."
    )

    try:
        bot = message.bot
        if file_type == "photo":
            sent = await bot.send_photo(
                config.admin_group_id,
                photo=file_id,
                caption=caption,
                parse_mode="HTML",
                reply_markup=admin_approval_keyboard(request_id),
            )
        else:
            sent = await bot.send_document(
                config.admin_group_id,
                document=file_id,
                caption=caption,
                parse_mode="HTML",
                reply_markup=admin_approval_keyboard(request_id),
            )

        # Save admin message reference for later edit
        await db.update_payment_admin_message(
            request_id=request_id,
            admin_chat_id=sent.chat.id,
            admin_message_id=sent.message_id,
        )
    except Exception as e:
        logger.error("Failed to forward receipt to admin group: %s", e, exc_info=True)
        await message.answer(
            "⚠️ Administratorga yuborishda muammo bo'ldi. Keyinroq urining."
        )
        await state.clear()
        return

    await message.answer(
        "✅ <b>Chek qabul qilindi!</b>\n\n"
        f"So'rov raqami: <code>#{request_id}</code>\n"
        f"Plan: <b>{plan.name_uz}</b>\n"
        f"Summa: <b>{format_amount(plan.price_uzs, 'UZS')}</b>\n\n"
        "⏳ Administrator chekni ko'rib chiqmoqda.\n"
        "Tasdiqlangach, sizga xabar beraman!\n\n"
        "<i>Odatda 1-24 soat ichida javob beriladi.</i>",
        parse_mode="HTML",
        reply_markup=main_reply_keyboard(),
    )
    await state.clear()
