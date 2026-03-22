"""Faster-whisper local STT engine for trevo.

Implements the :class:`core.stt_engine.STTEngine` ABC using the
``faster-whisper`` library for fully offline transcription.
"""

from __future__ import annotations

import io
from typing import AsyncGenerator, Optional

import numpy as np

from core.stt_engine import STTEngine, TranscriptEvent, WordInfo
from utils.audio_utils import pcm_to_wav
from utils.logger import logger

# Supported model sizes (smallest → largest)
MODEL_SIZES: list[str] = ["tiny", "base", "small", "medium", "large-v3"]


class WhisperLocalSTT(STTEngine):
    """Local speech-to-text via faster-whisper.

    The model is **lazily loaded** on the first call to :meth:`start_stream`,
    keeping startup fast when the user hasn't spoken yet.

    Parameters
    ----------
    model_size : str
        One of ``tiny``, ``base``, ``small``, ``medium``, ``large-v3``.
    device : str
        ``"auto"`` selects CUDA when available, otherwise CPU.
    compute_type : str
        Quantisation level — ``"int8"`` is a good default for speed.
    language : str | None
        ISO 639-1 code (e.g. ``"en"``).  ``None`` means auto-detect.
    """

    def __init__(
        self,
        model_size: str = "small",
        device: str = "auto",
        compute_type: str = "int8",
        language: Optional[str] = None,
    ) -> None:
        if model_size not in MODEL_SIZES:
            raise ValueError(
                f"Invalid model_size '{model_size}'. Choose from: {MODEL_SIZES}"
            )
        self._model_size = model_size
        self._device = device
        self._compute_type = compute_type
        self._language = language

        # Lazy-loaded model
        self._model: Optional[object] = None

        # Audio buffer: raw int16 PCM bytes accumulated during a stream
        self._audio_buffer: bytearray = bytearray()
        self._streaming = False

        logger.info(
            "WhisperLocalSTT configured (model={}, device={}, compute={})",
            model_size,
            device,
            compute_type,
        )

    # ------------------------------------------------------------------
    # Lazy model loading
    # ------------------------------------------------------------------

    def _ensure_model(self) -> None:
        """Load the faster-whisper model if not already loaded."""
        if self._model is not None:
            return

        logger.info("Loading faster-whisper model '{}' ...", self._model_size)

        try:
            from faster_whisper import WhisperModel
        except ImportError:
            raise RuntimeError(
                "faster-whisper is not installed. Run: pip install faster-whisper"
            )

        device = self._resolve_device()
        self._model = WhisperModel(
            self._model_size,
            device=device,
            compute_type=self._compute_type,
        )
        logger.info(
            "faster-whisper model '{}' loaded on {} (compute={})",
            self._model_size,
            device,
            self._compute_type,
        )

    def _resolve_device(self) -> str:
        """Resolve ``'auto'`` to ``'cuda'`` or ``'cpu'``."""
        if self._device != "auto":
            return self._device
        try:
            import torch

            if torch.cuda.is_available():
                logger.info("CUDA available — using GPU")
                return "cuda"
        except ImportError:
            pass
        logger.info("CUDA not available — using CPU")
        return "cpu"

    # ------------------------------------------------------------------
    # STTEngine interface
    # ------------------------------------------------------------------

    async def start_stream(self) -> None:
        """Prepare for a new transcription session."""
        self._ensure_model()
        self._audio_buffer.clear()
        self._streaming = True
        logger.debug("Whisper stream started")

    async def send_audio(self, chunk: bytes) -> None:
        """Buffer raw int16 PCM audio chunks."""
        if not self._streaming:
            return
        self._audio_buffer.extend(chunk)

    async def get_transcripts(self) -> AsyncGenerator[TranscriptEvent, None]:
        """Transcribe the buffered audio and yield final events.

        faster-whisper works in batch mode, so we transcribe the whole
        buffer once when results are requested.
        """
        if not self._audio_buffer:
            return

        audio_bytes = bytes(self._audio_buffer)
        wav_bytes = pcm_to_wav(audio_bytes)

        # faster-whisper accepts a file-like object
        wav_file = io.BytesIO(wav_bytes)

        try:
            segments, info = self._model.transcribe(  # type: ignore[union-attr]
                wav_file,
                language=self._language,
                beam_size=5,
                word_timestamps=True,
                vad_filter=True,
            )

            full_text_parts: list[str] = []
            all_words: list[WordInfo] = []

            for segment in segments:
                full_text_parts.append(segment.text.strip())
                if segment.words:
                    for w in segment.words:
                        all_words.append(
                            WordInfo(
                                word=w.word.strip(),
                                start_ms=int(w.start * 1000),
                                end_ms=int(w.end * 1000),
                                confidence=w.probability,
                            )
                        )

            full_text = " ".join(full_text_parts)
            if full_text:
                duration_ms = int(len(audio_bytes) / 2 / 16_000 * 1000)
                yield TranscriptEvent(
                    text=full_text,
                    is_final=True,
                    confidence=info.language_probability if info else 0.0,
                    language=info.language if info else "",
                    words=all_words,
                    duration_ms=duration_ms,
                )
                logger.info(
                    "Whisper transcription ({:.1f}s audio, lang={}): '{}'",
                    duration_ms / 1000,
                    info.language if info else "?",
                    full_text[:100],
                )

        except Exception:
            logger.exception("faster-whisper transcription failed")

    async def stop_stream(self) -> None:
        """End the current session."""
        self._streaming = False
        self._audio_buffer.clear()
        logger.debug("Whisper stream stopped")

