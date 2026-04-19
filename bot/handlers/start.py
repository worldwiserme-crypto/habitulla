"""/start, /help and main menu handlers."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from bot.keyboards.common import main_reply_keyboard
from bot.services.subscription_service import get_subscription_status_text

router = Router(name="start")

WELCOME_TEXT = """👋 <b>Assalomu alaykum, {name}!</b>

Men — odatlaringiz va budjetingizni kuzatuvchi AI botman.

<b>📝 Asosiy imkoniyatlar:</b>
• 🎯 Odat tracker — har kungi odatlar
• 💰 Budjet tracker — kirim va chiqim
• 👤 Mening kabinetim — shaxsiy statistika
• 📊 Hisobotlar — chiroyli Excel/PDF

<b>💬 Qanday ishlaydi?</b>
Pastdagi tugmalardan birini bosing va oddiy til bilan yozing yoki ayting:
• "Bugun 30 daqiqa yugurdim"
• "Taksiga 25 ming to'ladim"
• "Maosh 3 mln so'm"

AI o'zi tushunadi va to'g'ri joyga saqlaydi.

<b>🎤 Ovozli xabarlar</b> — Premium imkoniyat.

Boshlaymizmi? 👇"""

HELP_TEXT = """❓ <b>Yordam</b>

<b>🎯 Odat qo'shish:</b>
• "Bugun 30 daqiqa yugurdim"
• "Kitob 2 soat o'qidim"
• "100 marta otjimaniya qildim"

<b>💰 Chiqim qo'shish:</b>
• "Taksiga 25 ming to'ladim"
• "Nonvoydan 15 000 so'm non oldim"
• "Dorixonada 50 000 so'm sarfladim"

<b>💵 Kirim qo'shish:</b>
• "Oylik maosh 3 mln so'm"
• "Bonus 500 ming oldim"

<b>🎤 Ovozli xabar:</b>
Xuddi shu narsalarni ovoz bilan ham ayting.
<i>(Ovozli xabarlar — Premium funksiya)</i>

<b>📊 Buyruqlar:</b>
/start — asosiy menyu
/habits — bugungi odatlar
/budget — budjet holati
/report — Excel hisobot
/premium — Premium obuna
/settings — sozlamalar
/reset — barcha ma'lumotni o'chirish
/help — shu yordam

<b>💎 Status:</b> {status}"""


@router.message(CommandStart())
async def handle_start(message: Message, user: dict) -> None:
    name = user.get("full_name") or message.from_user.full_name or "do'st"
    await message.answer(
        WELCOME_TEXT.format(name=name),
        parse_mode="HTML",
        reply_markup=main_reply_keyboard(),
    )


@router.message(Command("help"))
@router.message(F.text == "❓ Yordam")
async def handle_help(message: Message, user: dict) -> None:
    status = await get_subscription_status_text(user["id"])
    await message.answer(
        HELP_TEXT.format(status=status),
        parse_mode="HTML",
        reply_markup=main_reply_keyboard(),
    )
