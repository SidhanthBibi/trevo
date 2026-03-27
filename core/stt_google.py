"""Google Cloud Speech-to-Text STT engine for trevo.

Uses the Google Cloud Speech-to-Text API v1 REST endpoint for
transcription.  Audio is buffered, converted to WAV, base64-encoded,
and sent via a synchronous ``speech:recognize`` request.

Free tier:
- 60 minutes of audio per month at no cost

Docs: https://cloud.google.com/speech-to-text/docs
API key: https://console.cloud.google.com/apis/credentials
"""

from __future__ import annotations

import base64
from typing import AsyncGenerator, Optional

from core.stt_engine import STTEngine, TranscriptEvent, WordInfo
from utils.logger import logger

_ENDPOINT = "https://speech.googleapis.com/v1/speech:recognize"


class GoogleCloudSTT(STTEngine):
    """Cloud STT via Google Cloud Speech-to-Text API v1.

    Audio is buffered during :meth:`send_audio` calls.  When
    :meth:`get_transcripts` is invoked the buffer is packed into a WAV
    file, base64-encoded, and sent to the ``speech:recognize`` endpoint.

    Parameters
    ----------
    api_key : str
        Google Cloud API key (passed as query parameter).
    model : str
        Recognition model — ``"default"``, ``"latest_short"``,
        ``"latest_long"``, ``"phone_call"``, ``"video"``, etc.
    language : str | None
        BCP-47 language code (e.g. ``"en-US"``).  Defaults to
        ``"en-US"`` if not provided.
    enable_word_time_offsets : bool
        Whether to request per-word timing information.
    """

    # Max chunk duration to stay under the 60-second sync API limit
    _MAX_CHUNK_SECONDS = 50
    _MAX_CHUNK_BYTES = _MAX_CHUNK_SECONDS * 16_000 * 2  # 16kHz, 16-bit mono

    def __init__(
        self,
        api_key: str = "",
        model: str = "default",
        language: Optional[str] = None,
        enable_word_time_offsets: bool = False,
        phrase_hints: Optional[list[str]] = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._language = language or "en-US"
        self._enable_word_time_offsets = enable_word_time_offsets
        self._phrase_hints: list[str] = phrase_hints or []

        self._audio_buffer: bytearray = bytearray()
        self._streaming = False

        logger.info(
            "GoogleCloudSTT configured (model={}, lang={}, hints={}, free 60 min/month)",
            model,
            self._language,
            len(self._phrase_hints),
        )

    # ------------------------------------------------------------------
    # STTEngine interface
    # ------------------------------------------------------------------

    async def start_stream(self) -> None:
        """Begin a new transcription session."""
        if not self._api_key:
            raise ValueError(
                "Google Cloud API key required. "
                "Get one at https://console.cloud.google.com/apis/credentials"
            )
        self._audio_buffer.clear()
        self._streaming = True
        logger.debug("Google Cloud STT stream started")

    async def send_audio(self, chunk: bytes) -> None:
        """Buffer raw int16 PCM audio."""
        if not self._streaming:
            return
        self._audio_buffer.extend(chunk)

    async def get_transcripts(self) -> AsyncGenerator[TranscriptEvent, None]:
        """Send buffered audio to Google Cloud STT and yield the transcript.

        Long recordings are automatically split into chunks of
        ``_MAX_CHUNK_SECONDS`` to stay under the sync API limit.
        """
        if not self._audio_buffer:
            return

        audio_bytes = bytes(self._audio_buffer)
        total_duration_ms = int(len(audio_bytes) / 2 / 16_000 * 1000)

        try:
            import httpx
        except ImportError:
            raise RuntimeError(
                "httpx package is not installed. Run: pip install httpx"
            )

        # Split into chunks if audio exceeds the sync API limit
        chunks: list[bytes] = []
        for i in range(0, len(audio_bytes), self._MAX_CHUNK_BYTES):
            chunks.append(audio_bytes[i : i + self._MAX_CHUNK_BYTES])

        logger.debug(
            "Google Cloud STT: {:.1f}s audio → {} chunk(s)",
            total_duration_ms / 1000,
            len(chunks),
        )

        url = f"{_ENDPOINT}?key={self._api_key}"
        all_texts: list[str] = []
        all_words: list[WordInfo] = []
        best_confidence = 0.0

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                for idx, chunk in enumerate(chunks):
                    chunk_duration_ms = int(len(chunk) / 2 / 16_000 * 1000)
                    audio_b64 = base64.b64encode(chunk).decode("ascii")

                    config: dict = {
                        "encoding": "LINEAR16",
                        "sampleRateHertz": 16000,
                        "languageCode": self._language,
                        "model": self._model,
                        "enableWordTimeOffsets": self._enable_word_time_offsets,
                    }

                    # Add phrase hints for improved accuracy
                    if self._phrase_hints:
                        config["speechContexts"] = [
                            {"phrases": self._phrase_hints, "boost": 10.0}
                        ]

                    payload = {"config": config, "audio": {"content": audio_b64}}

                    resp = await client.post(url, json=payload)
                    resp.raise_for_status()
                    data = resp.json()

                    results = data.get("results", [])
                    for result in results:
                        alternatives = result.get("alternatives", [])
                        if not alternatives:
                            continue

                        best = alternatives[0]
                        text = best.get("transcript", "").strip()
                        confidence = best.get("confidence", 0.0)

                        if not text:
                            continue

                        all_texts.append(text)
                        best_confidence = max(best_confidence, confidence)

                        if self._enable_word_time_offsets:
                            offset_ms = idx * self._MAX_CHUNK_SECONDS * 1000
                            for w in best.get("words", []):
                                all_words.append(
                                    WordInfo(
                                        word=w.get("word", ""),
                                        start_ms=_parse_duration_ms(w.get("startTime", "0s")) + offset_ms,
                                        end_ms=_parse_duration_ms(w.get("endTime", "0s")) + offset_ms,
                                        confidence=confidence,
                                    )
                                )

                    logger.debug(
                        "Chunk {}/{} ({:.1f}s): '{}'",
                        idx + 1, len(chunks),
                        chunk_duration_ms / 1000,
                        " ".join(all_texts[-1:])[:80],
                    )

            if all_texts:
                combined_text = " ".join(all_texts)
                yield TranscriptEvent(
                    text=combined_text,
                    is_final=True,
                    confidence=best_confidence,
                    language=self._language,
                    words=all_words,
                    duration_ms=total_duration_ms,
                )
                logger.info(
                    "Google Cloud transcription ({:.1f}s audio, {} chunks, model={}): '{}'",
                    total_duration_ms / 1000,
                    len(chunks),
                    self._model,
                    combined_text[:100],
                )

        except Exception:
            logger.exception("Google Cloud STT failed")

    async def recognize_interim(self, audio_bytes: bytes) -> str:
        """Quick recognition for real-time interim results during recording."""
        if not audio_bytes or not self._api_key:
            return ""

        try:
            import httpx

            # Use only the last ~15 seconds for speed (shorter audio = faster API response)
            max_bytes = 15 * 16_000 * 2  # 15s of 16kHz 16-bit mono
            if len(audio_bytes) > max_bytes:
                audio_bytes = audio_bytes[-max_bytes:]

            audio_b64 = base64.b64encode(audio_bytes).decode("ascii")
            config: dict = {
                "encoding": "LINEAR16",
                "sampleRateHertz": 16000,
                "languageCode": self._language,
                "model": "default",
                "enableWordTimeOffsets": False,
            }
            if self._phrase_hints:
                config["speechContexts"] = [
                    {"phrases": self._phrase_hints, "boost": 10.0}
                ]

            url = f"{_ENDPOINT}?key={self._api_key}"
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    url, json={"config": config, "audio": {"content": audio_b64}}
                )
                resp.raise_for_status()
                data = resp.json()

            texts = []
            for result in data.get("results", []):
                alts = result.get("alternatives", [])
                if alts:
                    t = alts[0].get("transcript", "").strip()
                    if t:
                        texts.append(t)
            return " ".join(texts)

        except Exception as exc:
            logger.debug("Interim recognition failed: {}", exc)
            return ""

    async def stop_stream(self) -> None:
        """End the current session and clear the buffer."""
        self._streaming = False
        self._audio_buffer.clear()
        logger.debug("Google Cloud STT stream stopped")


def _parse_duration_ms(duration_str: str) -> int:
    """Parse a Google protobuf Duration string (e.g. ``"1.500s"``) to ms."""
    if not duration_str:
        return 0
    # Strip trailing 's' and convert to milliseconds
    try:
        seconds = float(duration_str.rstrip("s"))
        return int(seconds * 1000)
    except (ValueError, AttributeError):
        return 0
