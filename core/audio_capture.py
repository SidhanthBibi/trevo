"""Microphone audio capture with sounddevice for trevo.

Provides callback-based capture via sounddevice.InputStream with a ring buffer,
RMS-based audio level calculation, and a configurable noise gate.
"""

from __future__ import annotations

import math
import threading
from collections import deque
from typing import Optional

import numpy as np
import sounddevice as sd
from PyQt6.QtCore import QObject, pyqtSignal

from utils.audio_utils import calculate_rms
from utils.logger import logger

# Audio capture constants
SAMPLE_RATE: int = 16_000
CHANNELS: int = 1
DTYPE: str = "int16"
CHUNK_SIZE: int = 512

# Ring buffer holds 30 seconds of audio
_RING_BUFFER_SECONDS: int = 30
_RING_BUFFER_CHUNKS: int = (_RING_BUFFER_SECONDS * SAMPLE_RATE) // CHUNK_SIZE


class AudioCapture(QObject):
    """Captures microphone audio and emits chunks + level signals."""

    audio_chunk = pyqtSignal(bytes)
    audio_level = pyqtSignal(float)

    def __init__(
        self,
        device: Optional[int] = None,
        noise_gate_threshold: float = 0.01,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self._device: Optional[int] = device
        self._noise_gate_threshold: float = noise_gate_threshold
        self._stream: Optional[sd.InputStream] = None
        self._ring_buffer: deque[bytes] = deque(maxlen=_RING_BUFFER_CHUNKS)
        self._lock = threading.Lock()
        self._running = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Open the audio stream and begin capturing."""
        if self._running:
            logger.warning("AudioCapture.start() called but already running")
            return

        logger.info(
            "Starting audio capture (device={}, rate={}, channels={}, chunk={})",
            self._device,
            SAMPLE_RATE,
            CHANNELS,
            CHUNK_SIZE,
        )
        self._stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype=DTYPE,
            blocksize=CHUNK_SIZE,
            device=self._device,
            callback=self._audio_callback,
        )
        self._stream.start()
        self._running = True

    def stop(self) -> None:
        """Stop and close the audio stream."""
        if not self._running:
            return
        logger.info("Stopping audio capture")
        self._running = False
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception as exc:
                logger.error("Error closing audio stream: {}", exc)
            finally:
                self._stream = None

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def noise_gate_threshold(self) -> float:
        return self._noise_gate_threshold

    @noise_gate_threshold.setter
    def noise_gate_threshold(self, value: float) -> None:
        self._noise_gate_threshold = max(0.0, value)

    def get_ring_buffer(self) -> bytes:
        """Return the full ring buffer contents as a single bytes object."""
        with self._lock:
            return b"".join(self._ring_buffer)

    # ------------------------------------------------------------------
    # Device enumeration
    # ------------------------------------------------------------------

    @staticmethod
    def list_devices() -> list[dict]:
        """Return a list of available input audio devices."""
        devices: list[dict] = []
        for idx, dev in enumerate(sd.query_devices()):
            if dev["max_input_channels"] > 0:  # type: ignore[index]
                devices.append(
                    {
                        "index": idx,
                        "name": dev["name"],  # type: ignore[index]
                        "channels": dev["max_input_channels"],  # type: ignore[index]
                        "sample_rate": dev["default_samplerate"],  # type: ignore[index]
                    }
                )
        return devices

    @staticmethod
    def default_device() -> Optional[int]:
        """Return the index of the default input device, or None."""
        try:
            info = sd.query_devices(kind="input")
            return int(info["index"])  # type: ignore[index]
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _audio_callback(
        self,
        indata: np.ndarray,
        frames: int,
        time_info: object,
        status: sd.CallbackFlags,
    ) -> None:
        """sounddevice callback — runs in a separate audio thread."""
        if status:
            logger.debug("Audio callback status: {}", status)

        raw: bytes = indata.tobytes()

        # RMS level (0.0 – 1.0 normalised for int16)
        rms = self._compute_rms(indata)
        self.audio_level.emit(rms)

        # Noise gate
        if rms < self._noise_gate_threshold:
            return

        with self._lock:
            self._ring_buffer.append(raw)

        self.audio_chunk.emit(raw)

    @staticmethod
    def _compute_rms(samples: np.ndarray) -> float:
        """Compute RMS level normalised to 0.0 – 1.0 for int16 data."""
        float_samples = samples.astype(np.float64)
        mean_sq = np.mean(float_samples ** 2)
        if mean_sq <= 0:
            return 0.0
        rms = math.sqrt(mean_sq) / 32768.0
        return min(rms, 1.0)
