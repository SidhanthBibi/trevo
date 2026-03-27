"""Real-time audio playback for Gemini Live responses.

Plays PCM audio chunks (24 kHz, 16-bit mono) received from the
Gemini Live API in near-real-time using sounddevice OutputStream.
"""

from __future__ import annotations

import queue
import threading
from typing import Optional

import numpy as np
import sounddevice as sd
from PyQt6.QtCore import QObject, pyqtSignal

from utils.logger import logger

# Gemini Live outputs 24 kHz 16-bit mono PCM
OUTPUT_SAMPLE_RATE = 24_000
OUTPUT_CHANNELS = 1
OUTPUT_DTYPE = "int16"
OUTPUT_BLOCKSIZE = 2400  # 100ms chunks at 24kHz


class AudioPlayer(QObject):
    """Streams PCM audio chunks to the speakers in real-time.

    Call :meth:`start` to open the output stream, then feed chunks via
    :meth:`play_chunk`.  Call :meth:`stop` to close.

    Signals
    -------
    playback_started()
        Audio started playing.
    playback_stopped()
        Audio stream closed or all queued audio drained.
    """

    playback_started = pyqtSignal()
    playback_stopped = pyqtSignal()

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._stream: Optional[sd.OutputStream] = None
        self._queue: queue.Queue[Optional[bytes]] = queue.Queue(maxsize=200)
        self._running = False
        self._playing = False

    def start(self) -> None:
        """Open the audio output stream."""
        if self._running:
            return

        # Clear any stale data
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break

        self._stream = sd.OutputStream(
            samplerate=OUTPUT_SAMPLE_RATE,
            channels=OUTPUT_CHANNELS,
            dtype=OUTPUT_DTYPE,
            blocksize=OUTPUT_BLOCKSIZE,
            callback=self._audio_callback,
        )
        self._stream.start()
        self._running = True
        logger.debug("AudioPlayer: output stream started ({}Hz)", OUTPUT_SAMPLE_RATE)

    def stop(self) -> None:
        """Stop and close the audio output stream."""
        if not self._running:
            return

        self._running = False

        # Signal the callback to stop
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            pass

        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception as exc:
                logger.debug("AudioPlayer: close error: {}", exc)
            self._stream = None

        self._playing = False
        self.playback_stopped.emit()
        logger.debug("AudioPlayer: stopped")

    def play_chunk(self, pcm_data: bytes) -> None:
        """Queue a PCM audio chunk for playback."""
        if not self._running:
            return
        try:
            self._queue.put_nowait(pcm_data)
            if not self._playing:
                self._playing = True
                self.playback_started.emit()
        except queue.Full:
            logger.debug("AudioPlayer: queue full, dropping chunk")

    def clear(self) -> None:
        """Clear all queued audio (for interruption handling)."""
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break
        self._playing = False

    @property
    def is_playing(self) -> bool:
        return self._playing

    def _audio_callback(
        self,
        outdata: np.ndarray,
        frames: int,
        time_info: object,
        status: sd.CallbackFlags,
    ) -> None:
        """sounddevice output callback — runs in audio thread."""
        if status:
            logger.debug("AudioPlayer callback status: {}", status)

        bytes_needed = frames * 2  # 16-bit = 2 bytes per sample
        collected = bytearray()

        while len(collected) < bytes_needed:
            try:
                chunk = self._queue.get_nowait()
                if chunk is None:
                    # Sentinel — fill rest with silence
                    collected.extend(b"\x00" * (bytes_needed - len(collected)))
                    self._playing = False
                    break
                collected.extend(chunk)
            except queue.Empty:
                # No more data — pad with silence
                collected.extend(b"\x00" * (bytes_needed - len(collected)))
                if self._playing and self._queue.empty():
                    self._playing = False
                break

        # Trim to exact size needed
        audio = collected[:bytes_needed]
        outdata[:] = np.frombuffer(bytes(audio), dtype=np.int16).reshape(-1, 1)
