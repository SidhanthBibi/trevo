"""Groq STT engine for trevo — FREE cloud transcription.

Groq offers Whisper Large V3 Turbo for FREE:
- 30 requests/min on free tier
- ~$0.011/hour on paid tier
- Blazing fast (10x faster than real-time)
- Supports 50+ languages

Note: Groq's Whisper API exists but is limited in free-tier quotas and
features compared to alternatives.  For best free STT, consider using
Gemini (``stt_gemini.py`` — 15 req/min via Google AI Studio, multimodal
audio support) or Google Cloud Speech-to-Text (``stt_google.py`` — 60 free
minutes/month with word-level timing).

Sign up: https://console.groq.com
"""

from __future__ import annotations

import io
from typing import AsyncGenerator, Optional

from core.stt_engine import STTEngine, TranscriptEvent, WordInfo
from utils.audio_utils import pcm_to_wav
from utils.logger import logger


class GroqSTT(STTEngine):
    """Cloud STT via Groq's Whisper API (free tier available).

    Uses the OpenAI-compatible API with Groq's base URL.
    Model: whisper-large-v3-turbo (or distil-whisper-large-v3-en)
    """

    def __init__(
        self,
        api_key: str = "",
        model: str = "whisper-large-v3-turbo",
        language: Optional[str] = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._language = language

        self._audio_buffer: bytearray = bytearray()
        self._streaming = False

        logger.info("GroqSTT configured (model={}, FREE tier)", model)

    async def start_stream(self) -> None:
        if not self._api_key:
            raise ValueError(
                "Groq API key required. Get one FREE at https://console.groq.com"
            )
        self._audio_buffer.clear()
        self._streaming = True
        logger.debug("Groq STT stream started")

    async def send_audio(self, chunk: bytes) -> None:
        if not self._streaming:
            return
        self._audio_buffer.extend(chunk)

    async def get_transcripts(self) -> AsyncGenerator[TranscriptEvent, None]:
        if not self._audio_buffer:
            return

        audio_bytes = bytes(self._audio_buffer)
        wav_bytes = pcm_to_wav(audio_bytes)
        duration_ms = int(len(audio_bytes) / 2 / 16_000 * 1000)

        try:
            import openai
        except ImportError:
            raise RuntimeError("openai package needed for Groq STT. Run: pip install openai")

        client = openai.AsyncOpenAI(
            api_key=self._api_key,
            base_url="https://api.groq.com/openai/v1",
        )

        try:
            wav_file = io.BytesIO(wav_bytes)
            wav_file.name = "audio.wav"

            kwargs: dict = {
                "model": self._model,
                "file": wav_file,
                "response_format": "verbose_json",
            }
            if self._language:
                kwargs["language"] = self._language

            response = await client.audio.transcriptions.create(**kwargs)

            text = ""
            words: list[WordInfo] = []
            language = ""

            if hasattr(response, "text"):
                text = response.text.strip()
            if hasattr(response, "language"):
                language = response.language or ""

            if text:
                yield TranscriptEvent(
                    text=text,
                    is_final=True,
                    confidence=1.0,
                    language=language,
                    words=words,
                    duration_ms=duration_ms,
                )
                logger.info(
                    "Groq transcription ({:.1f}s, model={}): '{}'",
                    duration_ms / 1000, self._model, text[:100],
                )

        except Exception:
            logger.exception("Groq STT failed")

    async def stop_stream(self) -> None:
        self._streaming = False
        self._audio_buffer.clear()
        logger.debug("Groq STT stream stopped")
