"""Report generation handler: /report → period → Excel or PDF."""
from __future__ import annotations

import os
from datetime import date, timedelta

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, FSInputFile, Message

from bot.config import config
from bot.keyboards.reports import report_format_keyboard, report_period_keyboard
from bot.services.db_service import db
from bot.services.excel_service import cleanup_file, generate_excel_report
from bot.services.pdf_service import cleanup_file as cleanup_pdf, generate_pdf_report
from bot.services.subscription_service import (
    can_use_custom_date_range,
    can_use_pdf_reports,
)
from bot.utils.formatters import format_date, today_local
from bot.utils.logger import logger

router = Router(name="reports")


@router.message(Command("report"))
async def cmd_report(message: Message) -> None:
    await message.answer(
        "📈 <b>Hisobot davrini tanlang:</b>",
        parse_mode="HTML",
        reply_markup=report_period_keyboard(),
    )


def _resolve_period(code: str) -> tuple[date, date]:
    today = today_local()
    if code == "week":
        return today - timedelta(days=6), today
    if code == "month":
        return today.replace(day=1), today
    if code == "last_week":
        end = today - timedelta(days=today.weekday() + 1)
        start = end - timedelta(days=6)
        return start, end
    if code == "last_month":
        first_this = today.replace(day=1)
        end = first_this - timedelta(days=1)
        return end.replace(day=1), end
    return today, today


@router.callback_query(F.data.startswith("report:"))
async def on_report_period(callback: CallbackQuery, user: dict) -> None:
    action = (callback.data or "").split(":", 1)[1]

    if action == "back":
        await callback.message.edit_text(
            "📈 <b>Hisobot davrini tanlang:</b>",
            parse_mode="HTML",
            reply_markup=report_period_keyboard(),
        )
        await callback.answer()
        return

    if action == "custom":
        await callback.message.edit_text(
            "📆 <b>Sana oralig'ini yuboring:</b>\n\n"
            "Format: <code>YYYY-MM-DD YYYY-MM-DD</code>\n"
            "Misol: <code>2026-04-01 2026-04-15</code>\n\n"
            "<i>Bepul tarifda maksimal " + str(config.free_report_max_days) + " kun.</i>",
            parse_mode="HTML",
        )
        await callback.answer()
        return

    start, end = _resolve_period(action)
    days = (end - start).days + 1

    if not await can_use_custom_date_range(user["id"], days):
        await callback.message.edit_text(
            f"📅 <b>Tanlangan davr: {days} kun</b>\n\n"
            f"Bepul tarifda maksimal {config.free_report_max_days} kun hisoboti mumkin.\n\n"
            "Cheksiz hisobot uchun: /premium",
            parse_mode="HTML",
        )
        await callback.answer()
        return

    await callback.message.edit_text(
        f"📅 <b>Davr:</b> {format_date(start)} — {format_date(end)}\n\n"
        "Qanday formatda yuborishni tanlang:",
        parse_mode="HTML",
        reply_markup=report_format_keyboard(action),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("format:"))
async def on_report_format(callback: CallbackQuery, user: dict) -> None:
    parts = (callback.data or "").split(":")
    if len(parts) < 3:
        await callback.answer("Xatolik", show_alert=True)
        return

    _, period_code, fmt = parts[0], parts[1], parts[2]
    start, end = _resolve_period(period_code)
    user_id = user["id"]
    currency = user.get("currency") or "UZS"

    if fmt == "pdf" and not await can_use_pdf_reports(user_id):
        await callback.message.edit_text(
            "📄 <b>PDF hisobot — Premium funksiya</b>\n\n"
            "Grafiklar, kategoriyalar, tahlillar bilan to'liq PDF faqat Premium.\n\n"
            "Premium olish: /premium",
            parse_mode="HTML",
        )
        await callback.answer()
        return

    await callback.message.edit_text(
        f"⏳ Hisobot tayyorlanmoqda... <i>({fmt.upper()})</i>",
        parse_mode="HTML",
    )
    await callback.answer()

    try:
        if fmt == "excel":
            path = await generate_excel_report(user_id, start, end)
            filename = f"hisobot_{start.isoformat()}_{end.isoformat()}.xlsx"
            caption = f"📊 <b>Excel hisobot</b>\n{format_date(start)} — {format_date(end)}"
            await callback.message.answer_document(
                FSInputFile(path, filename=filename),
                caption=caption,
                parse_mode="HTML",
            )
            cleanup_file(path)
            await db.log_metric("report_generated", user_id=user_id, metadata={"format": "excel"})
        else:
            path = await generate_pdf_report(user_id, start, end, currency=currency)
            filename = f"hisobot_{start.isoformat()}_{end.isoformat()}.pdf"
            caption = f"📄 <b>PDF hisobot</b>\n{format_date(start)} — {format_date(end)}"
            await callback.message.answer_document(
                FSInputFile(path, filename=filename),
                caption=caption,
                parse_mode="HTML",
            )
            cleanup_pdf(path)
            await db.log_metric("report_generated", user_id=user_id, metadata={"format": "pdf"})

        try:
            await callback.message.delete()
        except Exception:
            pass

    except Exception as e:
        logger.error("Report generation failed for %s: %s", user_id, e, exc_info=True)
        await callback.message.answer("⚠️ Hisobotni tayyorlashda xatolik yuz berdi.")


@router.message(F.text.regexp(r"^\d{4}-\d{2}-\d{2}\s+\d{4}-\d{2}-\d{2}$"))
async def on_custom_date_range(message: Message, user: dict) -> None:
    """Parse '2026-04-01 2026-04-15'."""
    try:
        parts = (message.text or "").split()
        start = date.fromisoformat(parts[0])
        end = date.fromisoformat(parts[1])
        if end < start:
            start, end = end, start
    except (ValueError, IndexError):
        await message.answer("❌ Format noto'g'ri. Misol: <code>2026-04-01 2026-04-15</code>", parse_mode="HTML")
        return

    days = (end - start).days + 1
    if not await can_use_custom_date_range(user["id"], days):
        await message.answer(
            f"📅 {days} kun — bepul tarifda maksimal {config.free_report_max_days} kun mumkin.\n\n"
            "Cheksiz: /premium"
        )
        return

    await message.answer(f"📅 <b>Davr:</b> {format_date(start)} — {format_date(end)}\n\nFormat tanlang:",
                         parse_mode="HTML",
                         reply_markup=report_format_keyboard(f"custom_{start.isoformat()}_{end.isoformat()}"))


@router.callback_query(F.data.startswith("format:custom_"))
async def on_custom_format(callback: CallbackQuery, user: dict) -> None:
    """Handle custom date range format selection."""
    parts = (callback.data or "").split(":")
    # format:custom_2026-04-01_2026-04-15:excel
    inner = parts[1]  # "custom_2026-04-01_2026-04-15"
    fmt = parts[2] if len(parts) > 2 else "excel"

    date_part = inner.replace("custom_", "")
    dates = date_part.split("_")
    if len(dates) != 2:
        await callback.answer("Xatolik", show_alert=True)
        return

    try:
        start = date.fromisoformat(dates[0])
        end = date.fromisoformat(dates[1])
    except ValueError:
        await callback.answer("Xatolik", show_alert=True)
        return

    user_id = user["id"]
    currency = user.get("currency") or "UZS"

    if fmt == "pdf" and not await can_use_pdf_reports(user_id):
        await callback.message.edit_text(
            "📄 PDF — Premium funksiya. /premium",
        )
        await callback.answer()
        return

    await callback.message.edit_text(f"⏳ Hisobot tayyorlanmoqda... ({fmt.upper()})")
    await callback.answer()

    try:
        if fmt == "excel":
            path = await generate_excel_report(user_id, start, end)
            await callback.message.answer_document(
                FSInputFile(path, filename=f"hisobot_{start}_{end}.xlsx"),
                caption=f"📊 {format_date(start)} — {format_date(end)}",
            )
            cleanup_file(path)
        else:
            path = await generate_pdf_report(user_id, start, end, currency=currency)
            await callback.message.answer_document(
                FSInputFile(path, filename=f"hisobot_{start}_{end}.pdf"),
                caption=f"📄 {format_date(start)} — {format_date(end)}",
            )
            cleanup_pdf(path)
        try:
            await callback.message.delete()
        except Exception:
            pass
    except Exception as e:
        logger.error("Custom report failed: %s", e, exc_info=True)
        await callback.message.answer("⚠️ Xatolik yuz berdi.")
