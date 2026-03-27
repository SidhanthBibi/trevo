"""Wake word detection for trevo using OpenWakeWord.

Listens for "Hey Trevo" (or a similar wake phrase) and emits a signal
when detected. Runs in a daemon thread to avoid blocking the UI.
"""

from __future__ import annotations

import threading
from typing import Optional

import numpy as np
from PyQt6.QtCore import QObject, pyqtSignal

from utils.logger import logger

# Try to import openwakeword — graceful degradation if not installed
_OWW_AVAILABLE = False
try:
    import openwakeword  # noqa: F401
    from openwakeword.model import Model as OWWModel
    _OWW_AVAILABLE = True
except ImportError:
    OWWModel = None  # type: ignore[assignment,misc]


class WakeWordDetector(QObject):
    """Detects a wake phrase from an audio stream using OpenWakeWord.

    Signals
    -------
    wake_word_detected()
        Emitted when the wake phrase confidence exceeds the threshold.
    """

    wake_word_detected = pyqtSignal()

    # OpenWakeWord processes audio in 80 ms frames at 16 kHz = 1280 samples
    _FRAME_SAMPLES = 1280
    _SAMPLE_RATE = 16000

    def __init__(
        self,
        threshold: float = 0.5,
        cooldown_seconds: float = 3.0,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self._threshold = threshold
        self._cooldown_samples = int(cooldown_seconds * self._SAMPLE_RATE)
        self._enabled = False
        self._model: Optional[OWWModel] = None
        self._buffer = np.array([], dtype=np.int16)
        self._samples_since_last_detection = self._cooldown_samples  # start ready
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def available(self) -> bool:
        """True if openwakeword is installed."""
        return _OWW_AVAILABLE

    def start(self) -> None:
        """Load the model and start listening."""
        if not _OWW_AVAILABLE:
            logger.warning("openwakeword not installed — wake word detection disabled")
            return

        if self._model is not None:
            return  # Already running

        try:
            # Use the built-in "hey jarvis" model as a stand-in for "hey trevo"
            # until a custom model is trained. Users can replace the model file.
            self._model = OWWModel(
                wakeword_models=["hey_jarvis_v0.1"],
                inference_framework="onnx",
            )
            self._enabled = True
            logger.info(
                "Wake word detector started (threshold={}, models={})",
                self._threshold,
                list(self._model.models.keys()),
            )
        except Exception:
            logger.exception("Failed to load wake word model")
            self._model = None

    def stop(self) -> None:
        """Stop listening and release the model."""
        self._enabled = False
        self._model = None
        self._buffer = np.array([], dtype=np.int16)
        logger.info("Wake word detector stopped")

    def process_audio(self, chunk: bytes) -> None:
        """Feed raw PCM16 audio into the detector.

        Called from the audio capture signal — runs on the capture thread.
        """
        if not self._enabled or self._model is None:
            return

        # Convert raw bytes to int16 numpy array
        audio = np.frombuffer(chunk, dtype=np.int16)

        with self._lock:
            self._buffer = np.concatenate([self._buffer, audio])
            self._samples_since_last_detection += len(audio)

            # Process complete 80 ms frames
            while len(self._buffer) >= self._FRAME_SAMPLES:
                frame = self._buffer[: self._FRAME_SAMPLES]
                self._buffer = self._buffer[self._FRAME_SAMPLES :]

                try:
                    prediction = self._model.predict(frame)
                except Exception:
                    continue

                # Check all model scores against threshold
                for model_name, score in prediction.items():
                    if (
                        score >= self._threshold
                        and self._samples_since_last_detection >= self._cooldown_samples
                    ):
                        logger.info(
                            "Wake word detected: {} (score={:.3f})",
                            model_name,
                            score,
                        )
                        self._samples_since_last_detection = 0
                        self.wake_word_detected.emit()
                        # Reset the model to avoid double-triggers
                        self._model.reset()
                        return
