"""OpenAI transcription STT engine for trevo.

Implements the :class:`core.stt_engine.STTEngine` ABC using OpenAI's
audio transcription API (whisper-1 or gpt-4o-transcribe models).
"""

from __future__ import annotations

import io
from typing import AsyncGenerator, Optional

from core.stt_engine import STTEngine, TranscriptEvent, WordInfo
from utils.audio_utils import pcm_to_wav
from utils.logger import logger


class OpenAISTT(STTEngine):
    """Cloud STT via OpenAI's transcription endpoint.

    Audio is buffered during :meth:`send_audio` calls.  When
    :meth:`get_transcripts` is invoked the buffer is packed into a WAV
    file and sent to the API in one request.

    Parameters
    ----------
    api_key : str
        OpenAI API key.
    model : str
        ``"whisper-1"`` or ``"gpt-4o-transcribe"``.
    language : str | None
        ISO 639-1 hint (e.g. ``"en"``).  ``None`` for auto-detection.
    """

    def __init__(
        self,
        api_key: str = "",
        model: str = "whisper-1",
        language: Optional[str] = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._language = language

        self._audio_buffer: bytearray = bytearray()
        self._streaming = False

        logger.info("OpenAISTT configured (model={})", model)

    # ------------------------------------------------------------------
    # STTEngine interface
    # ------------------------------------------------------------------

    async def start_stream(self) -> None:
        """Begin a new transcription session."""
        if not self._api_key:
            raise ValueError("OpenAI API key is required for OpenAISTT")
        self._audio_buffer.clear()
        self._streaming = True
        logger.debug("OpenAI STT stream started")

    async def send_audio(self, chunk: bytes) -> None:
        """Buffer raw int16 PCM audio."""
        if not self._streaming:
            return
        self._audio_buffer.extend(chunk)

    async def get_transcripts(self) -> AsyncGenerator[TranscriptEvent, None]:
        """Send buffered audio to OpenAI and yield the transcript."""
        if not self._audio_buffer:
            return

        audio_bytes = bytes(self._audio_buffer)
        wav_bytes = pcm_to_wav(audio_bytes)
        duration_ms = int(len(audio_bytes) / 2 / 16_000 * 1000)

        try:
            import openai
        except ImportError:
            raise RuntimeError("openai package is not installed. Run: pip install openai")

        client = openai.AsyncOpenAI(api_key=self._api_key)

        try:
            # Prepare file-like WAV for the API
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

            text: str = ""
            words: list[WordInfo] = []
            language: str = ""

            # The response shape varies by model; handle both forms.
            if hasattr(response, "text"):
                text = response.text.strip()
            if hasattr(response, "language"):
                language = response.language or ""
            if hasattr(response, "words") and response.words:
                for w in response.words:
                    words.append(
                        WordInfo(
                            word=w.word if hasattr(w, "word") else str(w.get("word", "")),
                            start_ms=int((w.start if hasattr(w, "start") else w.get("start", 0)) * 1000),
                            end_ms=int((w.end if hasattr(w, "end") else w.get("end", 0)) * 1000),
                            confidence=1.0,
                        )
                    )

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
                    "OpenAI transcription ({:.1f}s audio, model={}): '{}'",
                    duration_ms / 1000,
                    self._model,
                    text[:100],
                )

        except openai.APIConnectionError:
            logger.error("OpenAI API connection error — check your network")
        except openai.AuthenticationError:
            logger.error("OpenAI API authentication failed — check your API key")
        except openai.RateLimitError:
            logger.error("OpenAI API rate limit exceeded — try again shortly")
        except openai.APIStatusError as exc:
            logger.error("OpenAI API error (status {}): {}", exc.status_code, exc.message)
        except Exception:
            logger.exception("OpenAI transcription failed with unexpected error")

    async def stop_stream(self) -> None:
        """End the current session and clear the buffer."""
        self._streaming = False
        self._audio_buffer.clear()
        logger.debug("OpenAI STT stream stopped")

