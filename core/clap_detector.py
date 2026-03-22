"""Double-clap detector for trevo.

Analyses incoming PCM audio chunks for short impulsive sounds in the
800 Hz – 4 kHz band (where hand claps concentrate energy).  Emits a Qt
signal when a valid double-clap pattern is detected.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
from PyQt6.QtCore import QObject, pyqtSignal

from utils.logger import logger

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SAMPLE_RATE: int = 16_000
_SAMPLE_WIDTH: int = 2  # 16-bit PCM
_CLAP_BAND_LOW: int = 800
_CLAP_BAND_HIGH: int = 4000


# ---------------------------------------------------------------------------
# ClapDetector
# ---------------------------------------------------------------------------

class ClapDetector(QObject):
    """Detects double-claps from a 16-bit 16 kHz mono PCM audio stream.

    Algorithm
    ---------
    1. Convert raw bytes to float32 numpy array.
    2. Apply FFT-based bandpass filter (800 Hz – 4 kHz).
    3. Compute RMS energy of the filtered signal.
    4. Detect a *spike* when energy crosses *threshold* from below.
    5. If two spikes occur within *min_interval_ms* .. *max_interval_ms*
       → emit :pyqtSignal:`clap_detected`.
    6. After detection, ignore input for *cooldown_ms* to avoid
       re-triggering.

    Parameters
    ----------
    threshold:
        RMS energy threshold (0.0–1.0) for spike detection.
    min_interval_ms:
        Minimum gap between two claps (rejects single loud bangs).
    max_interval_ms:
        Maximum gap between two claps.
    cooldown_ms:
        Ignore period after a successful detection.
    """

    clap_detected = pyqtSignal()

    def __init__(
        self,
        threshold: float = 0.3,
        min_interval_ms: int = 100,
        max_interval_ms: int = 600,
        cooldown_ms: int = 2000,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)

        self._threshold: float = threshold
        self._min_interval_s: float = min_interval_ms / 1000.0
        self._max_interval_s: float = max_interval_ms / 1000.0
        self._cooldown_s: float = cooldown_ms / 1000.0

        # State
        self._prev_energy: float = 0.0
        self._last_spike_time: Optional[float] = None
        self._last_detection_time: float = 0.0
        self._enabled: bool = True

        logger.info(
            "ClapDetector initialised (threshold=%.2f, interval=%d–%d ms, cooldown=%d ms)",
            threshold, min_interval_ms, max_interval_ms, cooldown_ms,
        )

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def threshold(self) -> float:
        return self._threshold

    @threshold.setter
    def threshold(self, value: float) -> None:
        self._threshold = max(0.0, min(1.0, value))

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = value
        if not value:
            self._reset_state()
            logger.debug("ClapDetector disabled")
        else:
            logger.debug("ClapDetector enabled")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def process_audio(self, chunk: bytes) -> None:
        """Process a raw PCM audio chunk (16-bit, 16 kHz mono).

        Call this method repeatedly with consecutive audio chunks.
        """
        if not self._enabled:
            return

        now = time.monotonic()

        # Cooldown guard
        if now - self._last_detection_time < self._cooldown_s:
            return

        try:
            audio = self._bytes_to_float32(chunk)
            if len(audio) == 0:
                return

            filtered = self._bandpass_fft(audio, _SAMPLE_RATE, _CLAP_BAND_LOW, _CLAP_BAND_HIGH)
            energy = self._rms(filtered)

            is_spike = energy > self._threshold and self._prev_energy <= self._threshold
            self._prev_energy = energy

            if is_spike:
                self._handle_spike(now)

        except Exception as exc:  # noqa: BLE001
            logger.debug("ClapDetector.process_audio error: %s", exc)

    def reset(self) -> None:
        """Reset internal state (clear pending first-clap memory)."""
        self._reset_state()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _reset_state(self) -> None:
        self._prev_energy = 0.0
        self._last_spike_time = None

    def _handle_spike(self, now: float) -> None:
        """Evaluate whether a spike completes a double-clap pattern."""
        if self._last_spike_time is None:
            # First clap — remember it
            self._last_spike_time = now
            logger.debug("ClapDetector: first clap at %.3f", now)
            return

        gap = now - self._last_spike_time

        if gap < self._min_interval_s:
            # Too fast — likely the same clap's echo / ringing
            logger.debug("ClapDetector: spike gap %.3f s too short, ignoring", gap)
            return

        if gap > self._max_interval_s:
            # Too slow — treat this spike as a new first clap
            self._last_spike_time = now
            logger.debug("ClapDetector: spike gap %.3f s too long, resetting", gap)
            return

        # Valid double-clap!
        logger.info("ClapDetector: double-clap detected (gap=%.0f ms)", gap * 1000)
        self._last_detection_time = now
        self._last_spike_time = None
        self.clap_detected.emit()

    # ------------------------------------------------------------------
    # Signal processing helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _bytes_to_float32(chunk: bytes) -> np.ndarray:
        """Convert 16-bit PCM bytes to float32 in [-1.0, 1.0]."""
        audio_int16 = np.frombuffer(chunk, dtype=np.int16)
        return audio_int16.astype(np.float32) / 32768.0

    @staticmethod
    def _bandpass_fft(
        signal: np.ndarray,
        sample_rate: int,
        low_hz: int,
        high_hz: int,
    ) -> np.ndarray:
        """Apply a simple FFT-based bandpass filter.

        Zeroes out frequency bins outside the *low_hz* – *high_hz* range
        and transforms back to the time domain.
        """
        n = len(signal)
        if n == 0:
            return signal

        fft_data = np.fft.rfft(signal)
        freqs = np.fft.rfftfreq(n, d=1.0 / sample_rate)

        # Zero out bins outside the passband
        mask = (freqs >= low_hz) & (freqs <= high_hz)
        fft_data[~mask] = 0.0

        return np.fft.irfft(fft_data, n=n)

    @staticmethod
    def _rms(signal: np.ndarray) -> float:
        """Compute the root-mean-square energy of *signal*."""
        if len(signal) == 0:
            return 0.0
        return float(np.sqrt(np.mean(signal ** 2)))
