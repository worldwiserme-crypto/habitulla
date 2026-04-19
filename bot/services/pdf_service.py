"""PDF report generator with matplotlib charts — Premium feature."""
from __future__ import annotations

import asyncio
import io
import os
import tempfile
from datetime import date
from typing import Any, Dict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from bot.services.analytics_service import budget_summary, habit_summary
from bot.utils.formatters import format_amount, format_date
from bot.utils.logger import logger


def _chart_category_pie(categories: list[tuple[str, float]]) -> bytes:
    """Generate pie chart PNG bytes from categories list."""
    fig, ax = plt.subplots(figsize=(6, 4))
    if categories:
        labels = [c[0] for c in categories]
        sizes = [c[1] for c in categories]
        colors_list = ["#4472C4", "#ED7D31", "#A5A5A5", "#FFC000", "#70AD47", "#5B9BD5"]
        ax.pie(sizes, labels=labels, autopct="%1.1f%%",
               colors=colors_list[:len(labels)], startangle=90)
        ax.axis("equal")
    else:
        ax.text(0.5, 0.5, "Ma'lumot yo'q", ha="center", va="center", fontsize=14)
        ax.axis("off")

    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", dpi=120)
    plt.close(fig)
    buf.seek(0)
    return buf.getvalue()


def _chart_daily_trend(budget_logs: list[dict]) -> bytes:
    """Daily expense trend bar chart."""
    from collections import defaultdict
    daily: dict[str, float] = defaultdict(float)
    for log in budget_logs:
        if log.get("type") == "expense":
            daily[str(log.get("logged_date"))] += float(log.get("amount") or 0)

    fig, ax = plt.subplots(figsize=(8, 3.5))
    if daily:
        dates = sorted(daily.keys())
        values = [daily[d] for d in dates]
        ax.bar(range(len(dates)), values, color="#ED7D31")
        ax.set_xticks(range(len(dates)))
        ax.set_xticklabels([d[-5:] for d in dates], rotation=45, ha="right", fontsize=8)
        ax.set_ylabel("Chiqim")
        ax.set_title("Kunlik xarajat dinamikasi")
        ax.grid(axis="y", alpha=0.3)
    else:
        ax.text(0.5, 0.5, "Ma'lumot yo'q", ha="center", va="center", fontsize=14)
        ax.axis("off")

    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", dpi=120)
    plt.close(fig)
    buf.seek(0)
    return buf.getvalue()


async def generate_pdf_report(
    user_id: int, start: date, end: date, currency: str = "UZS"
) -> str:
    """Generate PDF report with charts. Returns temp file path."""
    from bot.services.db_service import db

    habit_stats, budget_stats, budget_logs = await asyncio.gather(
        habit_summary(user_id, start, end),
        budget_summary(user_id, start, end),
        db.get_budget_in_range(user_id, start, end),
    )

    def _build() -> str:
        tmp = tempfile.NamedTemporaryFile(
            delete=False,
            suffix=".pdf",
            prefix=f"hisobot_{user_id}_{start.isoformat()}_{end.isoformat()}_",
        )
        tmp.close()

        doc = SimpleDocTemplate(
            tmp.name,
            pagesize=A4,
            rightMargin=2 * cm,
            leftMargin=2 * cm,
            topMargin=2 * cm,
            bottomMargin=2 * cm,
        )

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            "Title", parent=styles["Heading1"], fontSize=20,
            textColor=colors.HexColor("#1F4E79"), alignment=1, spaceAfter=12,
        )
        h2 = ParagraphStyle(
            "H2", parent=styles["Heading2"], fontSize=14,
            textColor=colors.HexColor("#1F4E79"), spaceAfter=10,
        )
        body = ParagraphStyle("Body", parent=styles["BodyText"], fontSize=11, spaceAfter=6)

        story = []
        story.append(Paragraph(f"Shaxsiy hisobot", title_style))
        story.append(Paragraph(
            f"{format_date(start)} — {format_date(end)}", body
        ))
        story.append(Spacer(1, 0.5 * cm))

        # ─── HABITS ─────────────────────────────────
        story.append(Paragraph("Odatlar tahlili", h2))
        habit_table = [
            ["Jami log", str(habit_stats["total_logs"])],
            ["Noyob odatlar", str(habit_stats["unique_habits"])],
            ["Faol kunlar", f"{habit_stats['days_active']} / {habit_stats['days_total']}"],
            ["Izchillik (%)", f"{habit_stats['consistency_pct']}%"],
        ]
        t = Table(habit_table, colWidths=[7 * cm, 7 * cm])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#D9E1F2")),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("PADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(t)
        story.append(Spacer(1, 0.5 * cm))

        if habit_stats["top_habits"]:
            story.append(Paragraph("TOP-5 odatlar:", body))
            top_data = [["Odat", "Soni", "Jami"]]
            for h in habit_stats["top_habits"]:
                top_data.append([
                    h["name"], str(h["count"]), str(round(h["total_duration"], 1))
                ])
            t2 = Table(top_data, colWidths=[8 * cm, 3 * cm, 3 * cm])
            t2.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F4E79")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("PADDING", (0, 0), (-1, -1), 5),
            ]))
            story.append(t2)

        story.append(Spacer(1, 0.8 * cm))

        # ─── BUDGET ────────────────────────────────
        story.append(Paragraph("Budjet tahlili", h2))
        balance = budget_stats["balance"]
        budget_table = [
            ["Jami kirim", format_amount(budget_stats["total_income"], currency)],
            ["Jami chiqim", format_amount(budget_stats["total_expense"], currency)],
            ["Qoldiq", format_amount(balance, currency)],
            ["Kunlik o'rtacha chiqim", format_amount(budget_stats["avg_daily_expense"], currency)],
        ]
        bal_color = colors.HexColor("#C6EFCE") if balance >= 0 else colors.HexColor("#FFC7CE")
        t3 = Table(budget_table, colWidths=[7 * cm, 7 * cm])
        t3.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#D9E1F2")),
            ("BACKGROUND", (1, 2), (1, 2), bal_color),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            ("PADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(t3)
        story.append(Spacer(1, 0.5 * cm))

        # Pie chart
        pie_bytes = _chart_category_pie(budget_stats["top_categories"])
        story.append(Paragraph("Kategoriyalar bo'yicha xarajat:", body))
        story.append(Image(io.BytesIO(pie_bytes), width=14 * cm, height=9 * cm))
        story.append(Spacer(1, 0.3 * cm))

        # Trend chart
        trend_bytes = _chart_daily_trend(budget_logs)
        story.append(Image(io.BytesIO(trend_bytes), width=16 * cm, height=7 * cm))

        doc.build(story)
        return tmp.name

    loop = asyncio.get_running_loop()
    path = await loop.run_in_executor(None, _build)
    logger.info("PDF report generated: user=%s path=%s", user_id, path)
    return path


def cleanup_file(path: str) -> None:
    try:
        if os.path.exists(path):
            os.remove(path)
    except OSError as e:
        logger.warning("Failed to delete PDF %s: %s", path, e)
