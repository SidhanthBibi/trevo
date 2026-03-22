"""Deepgram Nova-3 streaming STT engine for trevo.

Connects to the Deepgram real-time transcription API via WebSocket and yields
interim / final transcript events.
"""

from __future__ import annotations

import asyncio
import json
from typing import AsyncGenerator, Optional
from urllib.parse import urlencode

import websockets
import websockets.client
from websockets.exceptions import ConnectionClosed

from core.stt_engine import STTEngine, TranscriptEvent, WordInfo
from utils.logger import logger

_DEEPGRAM_WS_URL = "wss://api.deepgram.com/v1/listen"

_DEFAULT_PARAMS: dict[str, str] = {
    "model": "nova-3",
    "language": "multi",
    "smart_format": "true",
    "interim_results": "true",
    "utterance_end_ms": "1000",
    "vad_events": "true",
    "filler_words": "false",
    "encoding": "linear16",
    "sample_rate": "16000",
    "channels": "1",
}

_MAX_RECONNECT_ATTEMPTS = 5
_RECONNECT_BASE_DELAY_S = 1.0


class DeepgramSTTEngine(STTEngine):
    """Streams audio to Deepgram Nova-3 and yields transcripts."""

    def __init__(self, api_key: str, extra_params: Optional[dict[str, str]] = None) -> None:
        self._api_key = api_key
        self._params = {**_DEFAULT_PARAMS, **(extra_params or {})}
        self._ws: Optional[websockets.client.WebSocketClientProtocol] = None
        self._receive_task: Optional[asyncio.Task[None]] = None
        self._transcript_queue: asyncio.Queue[TranscriptEvent] = asyncio.Queue()
        self._running = False
        self._reconnect_attempts = 0

    # ------------------------------------------------------------------
    # STTEngine interface
    # ------------------------------------------------------------------

    async def start_stream(self) -> None:
        """Open a WebSocket connection to Deepgram."""
        await self._connect()
        self._running = True
        self._reconnect_attempts = 0
        # Start background receiver
        self._receive_task = asyncio.create_task(self._receive_loop())
        logger.info("Deepgram streaming session started")

    async def send_audio(self, chunk: bytes) -> None:
        """Send raw int16 audio bytes to Deepgram."""
        if self._ws is None or not self._running:
            return
        try:
            await self._ws.send(chunk)
        except ConnectionClosed:
            logger.warning("WebSocket closed while sending audio, attempting reconnect")
            await self._handle_reconnect()

    async def get_transcripts(self) -> AsyncGenerator[TranscriptEvent, None]:
        """Yield TranscriptEvent objects as they arrive."""
        while self._running or not self._transcript_queue.empty():
            try:
                event = await asyncio.wait_for(self._transcript_queue.get(), timeout=0.5)
                yield event
            except asyncio.TimeoutError:
                continue

    async def stop_stream(self) -> None:
        """Gracefully close the Deepgram session."""
        self._running = False

        # Send close message per Deepgram protocol
        if self._ws is not None:
            try:
                close_msg = json.dumps({"type": "CloseStream"})
                await self._ws.send(close_msg)
            except Exception as exc:
                logger.debug("Error sending CloseStream: {}", exc)

        # Cancel receiver
        if self._receive_task is not None:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass
            self._receive_task = None

        # Close WebSocket
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception as exc:
                logger.debug("Error closing WebSocket: {}", exc)
            self._ws = None

        logger.info("Deepgram streaming session stopped")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _connect(self) -> None:
        """Establish the WebSocket connection."""
        query = urlencode(self._params)
        url = f"{_DEEPGRAM_WS_URL}?{query}"
        headers = {"Authorization": f"Token {self._api_key}"}

        logger.debug("Connecting to Deepgram: {}", url)
        self._ws = await websockets.client.connect(
            url,
            additional_headers=headers,
            ping_interval=20,
            ping_timeout=10,
        )
        logger.debug("Deepgram WebSocket connected")

    async def _receive_loop(self) -> None:
        """Continuously read messages from the WebSocket and enqueue transcripts."""
        while self._running:
            try:
                if self._ws is None:
                    await asyncio.sleep(0.1)
                    continue

                raw = await self._ws.recv()
                msg = json.loads(raw)
                self._process_message(msg)

            except ConnectionClosed:
                if self._running:
                    logger.warning("Deepgram WebSocket disconnected unexpectedly")
                    await self._handle_reconnect()
                else:
                    break
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Error in Deepgram receive loop: {}", exc)
                await asyncio.sleep(0.5)

    def _process_message(self, msg: dict) -> None:
        """Parse a Deepgram JSON message and enqueue a TranscriptEvent if applicable."""
        msg_type: str = msg.get("type", "")

        if msg_type == "Results":
            channel = msg.get("channel", {})
            alternatives = channel.get("alternatives", [])
            if not alternatives:
                return

            alt = alternatives[0]
            text: str = alt.get("transcript", "").strip()
            if not text:
                return

            is_final: bool = msg.get("is_final", False)
            confidence: float = alt.get("confidence", 0.0)
            language: str = channel.get("detected_language", "")

            words: list[WordInfo] = []
            for w in alt.get("words", []):
                words.append(
                    WordInfo(
                        word=w.get("word", ""),
                        start_ms=int(w.get("start", 0) * 1000),
                        end_ms=int(w.get("end", 0) * 1000),
                        confidence=w.get("confidence", 0.0),
                    )
                )

            duration_ms: int = int(msg.get("duration", 0) * 1000)

            event = TranscriptEvent(
                text=text,
                is_final=is_final,
                confidence=confidence,
                language=language,
                words=words,
                duration_ms=duration_ms,
            )
            self._transcript_queue.put_nowait(event)

        elif msg_type == "UtteranceEnd":
            logger.debug("Deepgram UtteranceEnd received")

        elif msg_type == "SpeechStarted":
            logger.debug("Deepgram SpeechStarted event")

        elif msg_type == "Metadata":
            logger.debug("Deepgram metadata: {}", msg)

        elif msg_type == "Error":
            logger.error("Deepgram error: {}", msg)

    async def _handle_reconnect(self) -> None:
        """Attempt to reconnect with exponential back-off."""
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None

        while self._running and self._reconnect_attempts < _MAX_RECONNECT_ATTEMPTS:
            self._reconnect_attempts += 1
            delay = _RECONNECT_BASE_DELAY_S * (2 ** (self._reconnect_attempts - 1))
            logger.info(
                "Reconnecting to Deepgram (attempt {}/{}) in {:.1f}s",
                self._reconnect_attempts,
                _MAX_RECONNECT_ATTEMPTS,
                delay,
            )
            await asyncio.sleep(delay)
            try:
                await self._connect()
                self._reconnect_attempts = 0
                logger.info("Deepgram reconnected successfully")
                return
            except Exception as exc:
                logger.error("Reconnect failed: {}", exc)

        if self._running:
            logger.error("Max reconnect attempts reached — giving up")
            self._running = False
