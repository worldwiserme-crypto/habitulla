"""Gemini AI service: text parsing + voice transcription.

UPDATED: Fallback to fast_parser when Gemini fails (quota, network, etc.)
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import tempfile
import traceback
from dataclasses import asdict, dataclass, field
from typing import List, Optional

import google.generativeai as genai
from pydub import AudioSegment

from bot.config import config
from bot.services.fast_parser import ParsedIntent, fast_parse
from bot.utils.logger import logger

genai.configure(api_key=config.gemini_api_key)

MODEL_NAME = "gemini-2.5-flash-lite"

PROMPT_TEMPLATE = """Sen o'zbek tilida yozilgan matndan ma'lumot ajratuvchi assistantsan.

Foydalanuvchi BITTA xabarda BIR YOKI BIR NECHTA odat/xarajat/kirim yozishi mumkin.
Matnni tahlil qilib HAR BIR harakatni alohida JSON obyekti sifatida qaytar.

MUHIM: Natijani har DOIM JSON array (massiv) sifatida qaytar, hatto bitta narsa bo'lsa ham.

Har bir obyekt quyidagi formatda:
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

Matn: "bugun 30 daqiqa yugurdim"
Javob: [{{"type": "HABIT_LOG", "habit_name": "Yugurish", "duration": 30, "duration_unit": "min", "date": "today", "confidence": 0.95}}]

Matn: "nonvoydan 15000 so'm non oldim"
Javob: [{{"type": "BUDGET_EXPENSE", "category": "oziq-ovqat", "amount": 15000, "currency": "UZS", "date": "today", "confidence": 0.95}}]

Matn: "taksiga 25 ming to'ladim"
Javob: [{{"type": "BUDGET_EXPENSE", "category": "transport", "amount": 25000, "currency": "UZS", "date": "today", "confidence": 0.95}}]

Matn: "BUGUN 4 SOAT YUGURDIM. 10 DAQIQA KITOB O'QIDIM. Dush qabul qildim"
Javob: [
  {{"type": "HABIT_LOG", "habit_name": "Yugurish", "duration": 4, "duration_unit": "hour", "date": "today", "confidence": 0.95}},
  {{"type": "HABIT_LOG", "habit_name": "Kitob o'qish", "duration": 10, "duration_unit": "min", "date": "today", "confidence": 0.95}},
  {{"type": "HABIT_LOG", "habit_name": "Dush qabul qilish", "date": "today", "confidence": 0.9}}
]

Matn: "nonga 15 ming, taksiga 25 ming ketdi"
Javob: [
  {{"type": "BUDGET_EXPENSE", "category": "oziq-ovqat", "amount": 15000, "currency": "UZS", "date": "today", "confidence": 0.9}},
  {{"type": "BUDGET_EXPENSE", "category": "transport", "amount": 25000, "currency": "UZS", "date": "today", "confidence": 0.95}}
]

Matn: "salom"
Javob: [{{"type": "UNKNOWN", "confidence": 0.0}}]

Matn: {user_message}

ESLATMA: Har doim JSON array qaytar, boshqa hech narsa yozma.
"""


@dataclass
class AIResult:
    intents: List[ParsedIntent] = field(default_factory=list)
    transcribed_text: Optional[str] = None
    used_ai: bool = False

    @property
    def intent(self) -> ParsedIntent:
        """Backward compatibility: return first intent."""
        if self.intents:
            return self.intents[0]
        return ParsedIntent(type="UNKNOWN", confidence=0.0)


class AIServiceError(Exception):
    pass


class AIService:
    def __init__(self) -> None:
        self.model = genai.GenerativeModel(MODEL_NAME)
        self._sem = asyncio.Semaphore(10)

    # ─── VOICE ──────────────────────────────────────────────
    async def transcribe_voice(self, ogg_path: str) -> str:
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
        """Parse user text into structured intent(s).
        
        Strategy:
        1. Try fast_parser first (free, 100ms)
        2. If confident (>=0.75), return it
        3. Otherwise call Gemini AI
        4. If Gemini fails (quota, network), fall back to fast_parser result
        """
        # 1. Try fast parser
        fast_result = fast_parse(text)
        if fast_result and fast_result.confidence >= 0.75:
            return AIResult(intents=[fast_result], used_ai=False)

        # 2. Fallback to Gemini (handles multi-intent + unclear messages)
        try:
            intents = await self._gemini_parse(text)
            return AIResult(intents=intents, used_ai=True)
        except AIServiceError as e:
            # Gemini yiqildi — fast_parser bor bo'lsa ishlataman
            logger.warning("Gemini unavailable, falling back. Reason: %s", e)
            if fast_result:
                return AIResult(intents=[fast_result], used_ai=False)
            # Hatto fast_parser ham yo'q — UNKNOWN qaytaramiz (xato ko'tarmaymiz!)
            return AIResult(
                intents=[ParsedIntent(type="UNKNOWN", confidence=0.0)],
                used_ai=False,
            )

    async def _gemini_parse(self, text: str) -> List[ParsedIntent]:
        async with self._sem:
            loop = asyncio.get_running_loop()
            try:
                raw = await loop.run_in_executor(
                    None, self._sync_text_call, text
                )
            except Exception as e:
                logger.error("Gemini parse failed: %s", e)
                raise AIServiceError("gemini_parse_failed") from e

        return self._parse_json_response(raw)

    def _sync_text_call(self, text: str) -> str:
        prompt = PROMPT_TEMPLATE.format(user_message=text[:1500])
        resp = self.model.generate_content(
            prompt,
            generation_config={
                "temperature": 0.1,
                "max_output_tokens": 1200,
                "response_mime_type": "application/json",
            },
        )
        return (resp.text or "").strip()

    def _parse_json_response(self, raw: str) -> List[ParsedIntent]:
        """Parse JSON response. Handles both array and single object formats."""
        text = raw.strip()
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

        try:
            data = json.loads(text)
        except (json.JSONDecodeError, ValueError):
            logger.warning("JSON parse failed on: %s", raw[:200])
            return [ParsedIntent(type="UNKNOWN", confidence=0.0)]

        # Normalize: always work with a list
        if isinstance(data, dict):
            data = [data]
        if not isinstance(data, list) or not data:
            return [ParsedIntent(type="UNKNOWN", confidence=0.0)]

        intents = []
        for item in data:
            if not isinstance(item, dict):
                continue
            intents.append(ParsedIntent(
                type=str(item.get("type", "UNKNOWN")).upper(),
                habit_name=item.get("habit_name"),
                duration=item.get("duration"),
                duration_unit=item.get("duration_unit"),
                amount=item.get("amount"),
                currency=(item.get("currency") or "UZS"),
                category=item.get("category"),
                date=item.get("date") or "today",
                note=item.get("note"),
                confidence=float(item.get("confidence") or 0.0),
            ))

        if not intents:
            return [ParsedIntent(type="UNKNOWN", confidence=0.0)]
        return intents

    # ─── PREMIUM: AI insights ───────────────────────────────
    async def generate_insights(self, stats_summary: str) -> str:
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
