"""Gemini multimodal STT engine for trevo — FREE cloud transcription.

Uses Google's Gemini 2.0 Flash model to transcribe audio via the
multimodal generateContent API.  Audio is sent as base64-encoded WAV
inline data and the model returns the transcript as text.

FREE tier (Google AI Studio API key):
- 15 requests/min
- No cost for light usage

Sign up: https://aistudio.google.com/apikey
"""

from __future__ import annotations

import base64
from typing import AsyncGenerator, Optional

from core.stt_engine import STTEngine, TranscriptEvent, WordInfo
from utils.audio_utils import pcm_to_wav
from utils.logger import logger

_ENDPOINT_BASE = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
)


class GeminiSTT(STTEngine):
    """Cloud STT via Google Gemini multimodal API (free tier available).

    Audio is buffered during :meth:`send_audio` calls.  When
    :meth:`get_transcripts` is invoked the buffer is packed into a WAV
    file, base64-encoded, and sent to the Gemini generateContent endpoint
    as inline audio data.

    Parameters
    ----------
    api_key : str
        Google AI Studio API key.
    model : str
        Gemini model name (default ``"gemini-2.0-flash"``).
    language : str | None
        Language hint for transcription (e.g. ``"en"``).  ``None`` for
        auto-detection.
    """

    def __init__(
        self,
        api_key: str = "",
        model: str = "gemini-2.0-flash",
        language: Optional[str] = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._language = language

        self._audio_buffer: bytearray = bytearray()
        self._streaming = False

        logger.info("GeminiSTT configured (model={}, FREE tier)", model)

    # ------------------------------------------------------------------
    # STTEngine interface
    # ------------------------------------------------------------------

    async def start_stream(self) -> None:
        """Begin a new transcription session."""
        if not self._api_key:
            raise ValueError(
                "Google AI Studio API key required. "
                "Get one FREE at https://aistudio.google.com/apikey"
            )
        self._audio_buffer.clear()
        self._streaming = True
        logger.debug("Gemini STT stream started")

    async def send_audio(self, chunk: bytes) -> None:
        """Buffer raw int16 PCM audio."""
        if not self._streaming:
            return
        self._audio_buffer.extend(chunk)

    async def get_transcripts(self) -> AsyncGenerator[TranscriptEvent, None]:
        """Send buffered audio to Gemini and yield the transcript."""
        if not self._audio_buffer:
            return

        audio_bytes = bytes(self._audio_buffer)
        wav_bytes = pcm_to_wav(audio_bytes)
        duration_ms = int(len(audio_bytes) / 2 / 16_000 * 1000)

        try:
            import httpx
        except ImportError:
            raise RuntimeError(
                "httpx package is not installed. Run: pip install httpx"
            )

        # Build the prompt — optionally include language hint
        prompt = "Transcribe the following audio exactly as spoken."
        if self._language:
            prompt += f" The audio is in language: {self._language}."
        prompt += (
            " Return ONLY the transcribed text, no commentary or formatting."
        )

        audio_b64 = base64.b64encode(wav_bytes).decode("ascii")

        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt},
                        {
                            "inline_data": {
                                "mime_type": "audio/wav",
                                "data": audio_b64,
                            }
                        },
                    ]
                }
            ]
        }

        url = f"{_ENDPOINT_BASE}{self._model}:generateContent?key={self._api_key}"

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                data = resp.json()

            # Extract text from the Gemini response
            text = ""
            try:
                candidates = data.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts:
                        text = parts[0].get("text", "").strip()
            except (IndexError, KeyError, TypeError):
                logger.warning("Unexpected Gemini response structure: {}", data)

            if text:
                yield TranscriptEvent(
                    text=text,
                    is_final=True,
                    confidence=1.0,
                    language=self._language or "",
                    words=[],
                    duration_ms=duration_ms,
                )
                logger.info(
                    "Gemini transcription ({:.1f}s audio, model={}): '{}'",
                    duration_ms / 1000,
                    self._model,
                    text[:100],
                )

        except Exception:
            logger.exception("Gemini STT failed")

    async def recognize_interim(self, audio_bytes: bytes) -> str:
        """Quick recognition for real-time interim results."""
        if not audio_bytes or not self._api_key:
            return ""

        # Use last ~10 seconds for speed
        max_bytes = 10 * 16_000 * 2
        if len(audio_bytes) > max_bytes:
            audio_bytes = audio_bytes[-max_bytes:]

        try:
            import httpx

            wav_bytes = pcm_to_wav(audio_bytes)
            audio_b64 = base64.b64encode(wav_bytes).decode("ascii")

            payload = {
                "contents": [{
                    "parts": [
                        {"text": "Transcribe this audio exactly. Return ONLY the text."},
                        {"inline_data": {"mime_type": "audio/wav", "data": audio_b64}},
                    ]
                }]
            }
            url = f"{_ENDPOINT_BASE}{self._model}:generateContent?key={self._api_key}"
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                data = resp.json()

            candidates = data.get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                if parts:
                    return parts[0].get("text", "").strip()
            return ""
        except Exception as exc:
            logger.debug("Gemini interim recognition failed: {}", exc)
            return ""

    async def stop_stream(self) -> None:
        """End the current session and clear the buffer."""
        self._streaming = False
        self._audio_buffer.clear()
        logger.debug("Gemini STT stream stopped")
