"""Groq AI service: text parsing + voice transcription.

Uses Groq API (Llama 3.3 70B) for text and Whisper Large v3 for voice.
Whisper Large v3 provides best multilingual support including Uzbek.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
from dataclasses import dataclass, field
from typing import List, Optional

from groq import Groq
from pydub import AudioSegment

from bot.config import config
from bot.services.fast_parser import ParsedIntent, fast_parse
from bot.utils.logger import logger

# Groq client
_groq_client = Groq(api_key=config.groq_api_key)

# Models
TEXT_MODEL = "llama-3.3-70b-versatile"       # Fast, smart, free
VOICE_MODEL = "whisper-large-v3"              # Full model (best for Uzbek)

# Prompt to help Whisper understand Uzbek context
VOICE_PROMPT = (
    "Bu o'zbek tilidagi ovoz yozuvi. "
    "Foydalanuvchi odat yoki xarajat haqida gapiryapti. "
    "Masalan: yugurdim, kitob o'qidim, non oldim, taksiga to'ladim, "
    "ming so'm, mln so'm, daqiqa, soat, kilometr."
)

PROMPT_TEMPLATE = """Sen o'zbek tilida yozilgan matndan ma'lumot ajratuvchi assistantsan.

Foydalanuvchi BITTA xabarda BIR YOKI BIR NECHTA odat/xarajat/kirim yozishi mumkin.
Matnni tahlil qilib HAR BIR harakatni alohida JSON obyekti sifatida qaytar.

MUHIM: Natijani har DOIM JSON array (massiv) sifatida qaytar, hatto bitta narsa bo'lsa ham.
Faqat JSON qaytar, boshqa hech narsa yozma.

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

Matn: "maosh 3 mln so'm"
Javob: [{{"type": "BUDGET_INCOME", "amount": 3000000, "currency": "UZS", "date": "today", "note": "maosh", "confidence": 0.95}}]

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
        if self.intents:
            return self.intents[0]
        return ParsedIntent(type="UNKNOWN", confidence=0.0)


class AIServiceError(Exception):
    pass


class AIService:
    def __init__(self) -> None:
        self._sem = asyncio.Semaphore(10)

    # ─── VOICE (Whisper Large v3) ──────────────────────────
    async def transcribe_voice(self, ogg_path: str) -> str:
        """Convert voice → text using Whisper Large v3 with Uzbek context."""
        mp3_path = ogg_path.replace(".ogg", ".mp3")
        try:
            await asyncio.get_running_loop().run_in_executor(
                None, self._convert_audio, ogg_path, mp3_path
            )
            transcription = await self._groq_transcribe(mp3_path)
            logger.info("Voice transcription: %s", transcription[:200])
            return transcription
        finally:
            for p in (ogg_path, mp3_path):
                try:
                    if os.path.exists(p):
                        os.remove(p)
                except OSError:
                    pass

    def _convert_audio(self, src: str, dst: str) -> None:
        """Convert OGG to MP3. Pad to 30s if shorter (Whisper requirement)."""
        audio = AudioSegment.from_file(src, format="ogg")
        # Whisper works best with audio >= 30 seconds
        if len(audio) < 30000:
            silence = AudioSegment.silent(duration=30000 - len(audio))
            audio = audio + silence
        audio.export(dst, format="mp3", bitrate="64k")

    async def _groq_transcribe(self, mp3_path: str) -> str:
        async with self._sem:
            try:
                loop = asyncio.get_running_loop()
                return await loop.run_in_executor(
                    None, self._sync_transcribe_call, mp3_path
                )
            except Exception as e:
                logger.error("Voice transcription failed: %s", e)
                raise AIServiceError("voice_transcription_failed") from e

    def _sync_transcribe_call(self, mp3_path: str) -> str:
        with open(mp3_path, "rb") as audio_file:
            transcription = _groq_client.audio.transcriptions.create(
                file=(os.path.basename(mp3_path), audio_file.read()),
                model=VOICE_MODEL,
                language="uz",
                prompt=VOICE_PROMPT,
                response_format="text",
                temperature=0.0,
            )
        return str(transcription).strip()

    # ─── TEXT PARSING ──────────────────────────────────────
    async def parse_intent(self, text: str) -> AIResult:
        """Parse user text into structured intent(s)."""
        # 1. Try fast parser first
        fast_result = fast_parse(text)
        if fast_result and fast_result.confidence >= 0.75:
            return AIResult(intents=[fast_result], used_ai=False)

        # 2. Fallback to Groq AI
        try:
            intents = await self._groq_parse(text)
            return AIResult(intents=intents, used_ai=True)
        except AIServiceError as e:
            logger.warning("Groq unavailable, falling back. Reason: %s", e)
            if fast_result:
                return AIResult(intents=[fast_result], used_ai=False)
            return AIResult(
                intents=[ParsedIntent(type="UNKNOWN", confidence=0.0)],
                used_ai=False,
            )

    async def _groq_parse(self, text: str) -> List[ParsedIntent]:
        async with self._sem:
            loop = asyncio.get_running_loop()
            try:
                raw = await loop.run_in_executor(
                    None, self._sync_text_call, text
                )
            except Exception as e:
                logger.error("Groq parse failed: %s", e)
                raise AIServiceError("groq_parse_failed") from e

        return self._parse_json_response(raw)

    def _sync_text_call(self, text: str) -> str:
        prompt = PROMPT_TEMPLATE.format(user_message=text[:1500])
        response = _groq_client.chat.completions.create(
            model=TEXT_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": "Sen JSON array qaytaradigan assistantsan. Boshqa hech narsa yozma."
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=1200,
            response_format={"type": "json_object"},
        )
        return (response.choices[0].message.content or "").strip()

    def _parse_json_response(self, raw: str) -> List[ParsedIntent]:
        """Parse JSON response. Handles array, single object, and wrapped formats."""
        text = raw.strip()
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

        try:
            data = json.loads(text)
        except (json.JSONDecodeError, ValueError):
            logger.warning("JSON parse failed on: %s", raw[:200])
            return [ParsedIntent(type="UNKNOWN", confidence=0.0)]

        # Groq sometimes wraps in {"intents": [...]} or {"result": [...]}
        if isinstance(data, dict):
            for key in ("intents", "result", "data", "items", "actions", "response"):
                if key in data and isinstance(data[key], list):
                    data = data[key]
                    break
            else:
                # Single object — wrap in list if it has a type field
                if "type" in data:
                    data = [data]
                else:
                    return [ParsedIntent(type="UNKNOWN", confidence=0.0)]

        if not isinstance(data, list) or not data:
            return [ParsedIntent(type="UNKNOWN", confidence=0.0)]

        intents = []
        for item in data:
            if not isinstance(item, dict):
                continue
            try:
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
            except (TypeError, ValueError) as e:
                logger.warning("Failed to parse intent item: %s", e)
                continue

        if not intents:
            return [ParsedIntent(type="UNKNOWN", confidence=0.0)]
        return intents

    # ─── PREMIUM: AI insights ──────────────────────────────
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
                    lambda: _groq_client.chat.completions.create(
