"""Gemini AI service: text parsing + voice transcription."""
from __future__ import annotations

import asyncio
import json
import os
import re
import tempfile
import traceback
from dataclasses import asdict, dataclass
from typing import Optional

import google.generativeai as genai
from pydub import AudioSegment

from bot.config import config
from bot.services.fast_parser import ParsedIntent, fast_parse
from bot.utils.logger import logger

genai.configure(api_key=config.gemini_api_key)

MODEL_NAME = "gemini-2.0-flash"

PROMPT_TEMPLATE = """Sen o'zbek tilida yozilgan matndan ma'lumot ajratuvchi assistantsan. Foydalanuvchi kundalik odat yoki xarajatini yozadi. Matnni tahlil qilib FAQAT quyidagi JSON formatda qaytar, boshqa hech narsa yozma:

{{
  "type": "HABIT_LOG | BUDGET_EXPENSE | BUDGET_INCOME | UNKNOWN",
  "habit_name": "string yoki null",
  "duration": number_yoki_null,
  "duration_unit": "min | hour | count | page | km | null",
  "amount": number_yoki_null,
  "currency": "UZS | USD | EUR | RUB | null",
  "category": "oziq-ovqat | transport | soglik | kiyim | kommunal | ta'lim | ko'ngil-ochar | boshqa | null",
  "date": "today | yesterday | YYYY-MM-DD",
  "note": "qisqa izoh yoki null",
  "confidence": 0.0_dan_1.0_gacha
}}

Misollar:
- "bugun 30 daqiqa yugurdim" → HABIT_LOG, habit_name: "Yugurish", duration: 30, duration_unit: "min"
- "nonvoydan 15000 so'm non oldim" → BUDGET_EXPENSE, category: "oziq-ovqat", amount: 15000, currency: "UZS"
- "oylik maosh 3000000 so'm" → BUDGET_INCOME, amount: 3000000, currency: "UZS"
- "taksiga 25 ming to'ladim" → BUDGET_EXPENSE, category: "transport", amount: 25000, currency: "UZS"
- "kitob 2 soat o'qidim" → HABIT_LOG, habit_name: "Kitob o'qish", duration: 2, duration_unit: "hour"
- "salom" → UNKNOWN, confidence: 0.0

Matn: {user_message}
"""


@dataclass
class AIResult:
    intent: ParsedIntent
    transcribed_text: Optional[str] = None
    used_ai: bool = False


class AIServiceError(Exception):
    pass


class AIService:
    def __init__(self) -> None:
        self.model = genai.GenerativeModel(MODEL_NAME)
        self._sem = asyncio.Semaphore(10)  # Concurrent API calls

    # ─── VOICE ──────────────────────────────────────────────
    async def transcribe_voice(self, ogg_path: str) -> str:
        """Convert .ogg → .mp3, send to Gemini, return transcription."""
        mp3_path = ogg_path.replace(".ogg", ".mp3")
        try:
            await asyncio.get_running_loop().run_in_executor(
                None, self._convert_audio, ogg_path, mp3_path
            )
            transcription = await self._gemini_audio(mp3_path)
            return transcription
        finally:
            for p in (ogg_path, mp3_path):
                try:
                    if os.path.exists(p):
                        os.remove(p)
                except OSError:
                    pass

    def _convert_audio(self, src: str, dst: str) -> None:
        audio = AudioSegment.from_file(src, format="ogg")
        audio.export(dst, format="mp3", bitrate="64k")

    async def _gemini_audio(self, mp3_path: str) -> str:
        async with self._sem:
            try:
                loop = asyncio.get_running_loop()
                return await loop.run_in_executor(
                    None, self._sync_audio_call, mp3_path
                )
            except Exception as e:
                logger.error("Voice transcription failed: %s", e)
                raise AIServiceError("voice_transcription_failed") from e

    def _sync_audio_call(self, mp3_path: str) -> str:
        uploaded = genai.upload_file(mp3_path, mime_type="audio/mp3")
        try:
            resp = self.model.generate_content([
                "Quyidagi ovozni o'zbek tilida matnga aylantir. FAQAT matnning o'zini qaytar, boshqa hech narsa yozma.",
                uploaded,
            ])
            return (resp.text or "").strip()
        finally:
            try:
                genai.delete_file(uploaded.name)
            except Exception:
                pass

    # ─── TEXT PARSING ───────────────────────────────────────
    async def parse_intent(self, text: str) -> AIResult:
        """Parse user text into structured intent. Uses fast parser first."""
        # 1. Try fast parser
        fast_result = fast_parse(text)
        if fast_result and fast_result.confidence >= 0.75:
            return AIResult(intent=fast_result, used_ai=False)

        # 2. Fallback to Gemini
        try:
            intent = await self._gemini_parse(text)
            return AIResult(intent=intent, used_ai=True)
        except AIServiceError:
            # If AI fails but we had a low-confidence fast result, use it
            if fast_result:
                return AIResult(intent=fast_result, used_ai=False)
            raise

    async def _gemini_parse(self, text: str) -> ParsedIntent:
        async with self._sem:
            loop = asyncio.get_running_loop()
            try:
                raw = await loop.run_in_executor(
                    None, self._sync_text_call, text
                )
            except Exception as e:
                logger.error("Gemini parse failed: %s\n%s", e, traceback.format_exc())
                raise AIServiceError("gemini_parse_failed") from e

        return self._parse_json_response(raw)

    def _sync_text_call(self, text: str) -> str:
        prompt = PROMPT_TEMPLATE.format(user_message=text[:1500])
        resp = self.model.generate_content(
            prompt,
            generation_config={
                "temperature": 0.1,
                "max_output_tokens": 400,
                "response_mime_type": "application/json",
            },
        )
        return (resp.text or "").strip()

    def _parse_json_response(self, raw: str) -> ParsedIntent:
        """Strip code fences, parse JSON, validate."""
        text = raw.strip()
        # Remove markdown fences if present
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

        try:
            data = json.loads(text)
        except (json.JSONDecodeError, ValueError):
            logger.warning("JSON parse failed on: %s", raw[:200])
            return ParsedIntent(type="UNKNOWN", confidence=0.0)

        return ParsedIntent(
            type=str(data.get("type", "UNKNOWN")).upper(),
            habit_name=data.get("habit_name"),
            duration=data.get("duration"),
            duration_unit=data.get("duration_unit"),
            amount=data.get("amount"),
            currency=(data.get("currency") or "UZS"),
            category=data.get("category"),
            date=data.get("date") or "today",
            note=data.get("note"),
            confidence=float(data.get("confidence") or 0.0),
        )

    # ─── PREMIUM: AI insights ───────────────────────────────
    async def generate_insights(self, stats_summary: str) -> str:
        """Generate personalized insights from stats (Premium feature)."""
        prompt = f"""Sen shaxsiy salomatlik va moliya maslahatchisisan. Quyidagi foydalanuvchi statistikasini tahlil qilib, o'zbek tilida 3-5 ta qisqa, amaliy va motivatsion maslahat ber. Har bir maslahat 1-2 gap bo'lsin. Markdown ishlat.

Statistika:
{stats_summary}

FORMAT:
💡 **Insayt va Maslahatlar**

1. [maslahat]
2. [maslahat]
...
"""
        async with self._sem:
            loop = asyncio.get_running_loop()
            try:
                resp = await loop.run_in_executor(
                    None,
                    lambda: self.model.generate_content(
                        prompt,
                        generation_config={
                            "temperature": 0.7,
                            "max_output_tokens": 600,
                        },
                    ),
                )
                return (resp.text or "").strip()
            except Exception as e:
                logger.error("Insight generation failed: %s", e)
                raise AIServiceError("insight_failed") from e


ai = AIService()
