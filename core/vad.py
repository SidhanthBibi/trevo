"""Voice Activity Detection for trevo.

Attempts Silero VAD (torch) first, then webrtcvad, then a simple energy-based
fallback.  Emits speech_start / speech_end signals and returns speech segments.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
from PyQt6.QtCore import QObject, pyqtSignal

from utils.audio_utils import bytes_to_pcm, calculate_rms, int16_to_float32
from utils.logger import logger

# Default timing parameters (seconds)
_DEFAULT_SILENCE_THRESHOLD_S: float = 0.500
_DEFAULT_PADDING_S: float = 0.300


@dataclass
class SpeechSegment:
    """A contiguous speech segment."""

    audio: bytes
    start_time: float
    end_time: float


class _Backend:
    """Internal ABC for VAD backends."""

    def is_speech(self, chunk: bytes, sample_rate: int) -> bool:
        raise NotImplementedError


# ------------------------------------------------------------------
# Backend: Silero VAD (best quality)
# ------------------------------------------------------------------

class _SileroBackend(_Backend):
    def __init__(self) -> None:
        import torch  # noqa: F811

        model, utils = torch.hub.load(
            repo_or_dir="snakers4/silero-vad",
            model="silero_vad",
            force_reload=False,
            trust_repo=True,
        )
        self._model = model
        self._torch = torch
        logger.info("Silero VAD backend loaded")

    def is_speech(self, chunk: bytes, sample_rate: int) -> bool:
        audio_int16 = np.frombuffer(chunk, dtype=np.int16)
        audio_float = audio_int16.astype(np.float32) / 32768.0
        tensor = self._torch.from_numpy(audio_float)
        prob: float = self._model(tensor, sample_rate).item()
        return prob > 0.5


# ------------------------------------------------------------------
# Backend: webrtcvad
# ------------------------------------------------------------------

class _WebRTCBackend(_Backend):
    def __init__(self, aggressiveness: int = 3) -> None:
        import webrtcvad

        self._vad = webrtcvad.Vad(aggressiveness)
        logger.info("webrtcvad backend loaded (aggressiveness={})", aggressiveness)

    def is_speech(self, chunk: bytes, sample_rate: int) -> bool:
        # webrtcvad requires frames of 10, 20, or 30 ms.
        frame_duration_ms = len(chunk) // (2 * sample_rate // 1000)
        if frame_duration_ms not in (10, 20, 30):
            # Truncate / pad to 30 ms frame
            frame_bytes = 2 * sample_rate * 30 // 1000
            chunk = chunk[:frame_bytes].ljust(frame_bytes, b"\x00")
        return self._vad.is_speech(chunk, sample_rate)


# ------------------------------------------------------------------
# Backend: simple energy
# ------------------------------------------------------------------

class _EnergyBackend(_Backend):
    def __init__(self, energy_threshold: float = 500.0) -> None:
        self._threshold = energy_threshold
        logger.info("Energy-based VAD backend loaded (threshold={})", energy_threshold)

    def is_speech(self, chunk: bytes, sample_rate: int) -> bool:
        samples = np.frombuffer(chunk, dtype=np.int16).astype(np.float64)
        rms = np.sqrt(np.mean(samples ** 2)) if len(samples) > 0 else 0.0
        return rms > self._threshold


# ------------------------------------------------------------------
# Public VAD class
# ------------------------------------------------------------------

class VoiceActivityDetector(QObject):
    """Processes audio chunks and emits speech_start / speech_end signals."""

    speech_start = pyqtSignal()
    speech_end = pyqtSignal()

    def __init__(
        self,
        sample_rate: int = 16_000,
        silence_threshold_s: float = _DEFAULT_SILENCE_THRESHOLD_S,
        padding_s: float = _DEFAULT_PADDING_S,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self._sample_rate = sample_rate
        self._silence_threshold_s = silence_threshold_s
        self._padding_s = padding_s

        self._backend = self._load_backend()
        self._in_speech = False
        self._speech_start_time: float = 0.0
        self._last_speech_time: float = 0.0
        self._segment_audio: list[bytes] = []

        # Max padding buffer chunks (pre-speech) — use deque for O(1) rotation
        bytes_per_second = sample_rate * 2  # int16
        self._max_padding_chunks = max(1, int(padding_s * bytes_per_second / 512))
        self._padding_buffer: deque[bytes] = deque(maxlen=self._max_padding_chunks)

    # ------------------------------------------------------------------
    # Backend selection
    # ------------------------------------------------------------------

    @staticmethod
    def _load_backend() -> _Backend:
        """Try Silero -> webrtcvad -> energy fallback."""
        try:
            return _SileroBackend()
        except Exception as exc:
            logger.debug("Silero VAD unavailable: {}", exc)

        try:
            return _WebRTCBackend()
        except Exception as exc:
            logger.debug("webrtcvad unavailable: {}", exc)

        return _EnergyBackend()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def process_chunk(self, chunk: bytes) -> Optional[SpeechSegment]:
        """Feed an audio chunk and possibly receive a completed SpeechSegment.

        Also emits speech_start / speech_end signals at the appropriate moments.
        """
        now = time.monotonic()
        is_speech = self._backend.is_speech(chunk, self._sample_rate)

        if is_speech:
            if not self._in_speech:
                # Transition: silence -> speech
                self._in_speech = True
                self._speech_start_time = now - self._padding_s
                self._segment_audio = list(self._padding_buffer)
                self.speech_start.emit()
                logger.debug("Speech started")

            self._last_speech_time = now
            self._segment_audio.append(chunk)
            return None

        # Not speech -------------------------------------------------------
        # Keep a rolling padding buffer for pre-speech context (deque auto-evicts)
        self._padding_buffer.append(chunk)

        if self._in_speech:
            self._segment_audio.append(chunk)

            # Check if silence has exceeded the threshold
            silence_duration = now - self._last_speech_time
            if silence_duration >= self._silence_threshold_s:
                # Transition: speech -> silence
                self._in_speech = False
                segment = SpeechSegment(
                    audio=b"".join(self._segment_audio),
                    start_time=self._speech_start_time,
                    end_time=now,
                )
                self._segment_audio.clear()
                self.speech_end.emit()
                logger.debug(
                    "Speech ended (duration={:.2f}s)",
                    segment.end_time - segment.start_time,
                )
                return segment

        return None

    def reset(self) -> None:
        """Reset internal state."""
        self._in_speech = False
        self._segment_audio.clear()
        self._padding_buffer.clear()
        self._speech_start_time = 0.0
        self._last_speech_time = 0.0

    @property
    def in_speech(self) -> bool:
        return self._in_speech
