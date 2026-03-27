"""Gemini Live API integration for real-time bidirectional voice in Trevo Mode.

Uses the Gemini Multimodal Live API over WebSocket for true real-time
voice conversation — no record-stop-process-respond cycle.  Audio flows
in both directions simultaneously with built-in VAD, interruption handling,
and automatic turn management.

Endpoint: wss://generativelanguage.googleapis.com/ws/...
Audio in:  PCM 16-bit 16 kHz mono (same as our mic capture)
Audio out: PCM 16-bit 24 kHz mono
"""

from __future__ import annotations

import asyncio
import base64
import json
from typing import Optional

from PyQt6.QtCore import QObject, pyqtSignal

from utils.logger import logger

_WS_ENDPOINT = (
    "wss://generativelanguage.googleapis.com/ws/"
    "google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent"
)

# Models that support bidiGenerateContent (ordered by preference)
_LIVE_MODELS = [
    "gemini-2.5-flash-native-audio-latest",
    "gemini-3.1-flash-live-preview",
    "gemini-2.5-flash-native-audio-preview-12-2025",
]


class GeminiLiveSession(QObject):
    """Manages a real-time voice session with the Gemini Live API.

    Signals
    -------
    audio_response(bytes)
        Raw PCM audio from the model (24 kHz, 16-bit mono).
    text_response(str)
        Transcript of the model's spoken response.
    user_transcript(str)
        Transcript of the user's speech (from Gemini's built-in STT).
    turn_complete()
        Emitted when the model finishes a response turn.
    session_started()
        WebSocket connected and setup acknowledged.
    session_error(str)
        Error message if something goes wrong.
    session_ended()
        Session closed (normally or on error).
    """

    audio_response = pyqtSignal(bytes)
    text_response = pyqtSignal(str)
    user_transcript = pyqtSignal(str)
    turn_complete = pyqtSignal()
    session_started = pyqtSignal()
    session_error = pyqtSignal(str)
    session_ended = pyqtSignal()

    def __init__(
        self,
        api_key: str,
        system_prompt: str = "",
        voice: str = "Kore",
        model: str = "gemini-2.5-flash-native-audio-latest",
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self._api_key = api_key
        self._system_prompt = system_prompt or self._default_system_prompt()
        self._voice = voice
        self._model = model

        self._ws: Optional[object] = None  # websockets connection
        self._connected = False
        self._receive_task: Optional[asyncio.Task] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    @staticmethod
    def _default_system_prompt() -> str:
        return (
            "You are Trevo, a helpful AI voice assistant running on the user's "
            "Windows desktop. You speak naturally and conversationally. "
            "Keep responses concise (1-3 sentences) unless asked for detail. "
            "The user's name is Sidhanth. Be friendly and efficient."
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Open WebSocket and send setup message. Tries fallback models."""
        try:
            import websockets
        except ImportError:
            self.session_error.emit(
                "websockets package required. Run: pip install websockets"
            )
            return

        # Build list of models to try (user-specified first, then fallbacks)
        models_to_try = [self._model]
        for m in _LIVE_MODELS:
            if m not in models_to_try:
                models_to_try.append(m)

        url = f"{_WS_ENDPOINT}?key={self._api_key}"
        last_error = ""

        for model_name in models_to_try:
            logger.info("Gemini Live: trying model {}", model_name)

            try:
                ws = await websockets.connect(  # type: ignore[attr-defined]
                    url,
                    additional_headers={"Content-Type": "application/json"},
                    max_size=None,
                    ping_interval=30,
                    ping_timeout=10,
                    close_timeout=5,
                )
            except Exception as exc:
                logger.error("Gemini Live: WebSocket connect failed: {}", exc)
                self.session_error.emit(f"Connection failed: {exc}")
                return

            # Send setup message
            setup_msg = {
                "setup": {
                    "model": f"models/{model_name}",
                    "generationConfig": {
                        "responseModalities": ["AUDIO"],
                        "speechConfig": {
                            "voiceConfig": {
                                "prebuiltVoiceConfig": {
                                    "voiceName": self._voice,
                                }
                            }
                        },
                    },
                    "systemInstruction": {
                        "parts": [{"text": self._system_prompt}]
                    },
                    "inputAudioTranscription": {},
                    "outputAudioTranscription": {},
                    "realtimeInputConfig": {
                        "automaticActivityDetection": {
                            "startOfSpeechSensitivity": "START_SENSITIVITY_HIGH",
                            "endOfSpeechSensitivity": "END_SENSITIVITY_HIGH",
                            "prefixPaddingMs": 20,
                            "silenceDurationMs": 500,
                        }
                    },
                }
            }

            try:
                await ws.send(json.dumps(setup_msg))
                raw = await asyncio.wait_for(ws.recv(), timeout=10.0)
                resp = json.loads(raw)

                if "setupComplete" in resp:
                    self._ws = ws
                    self._model = model_name
                    self._connected = True
                    logger.info("Gemini Live: session established (model={}, voice={})",
                                model_name, self._voice)
                    self.session_started.emit()
                    # Start background receive loop
                    self._loop = asyncio.get_event_loop()
                    self._receive_task = asyncio.create_task(self._receive_loop())
                    return  # success

                last_error = f"Unexpected response for {model_name}: {resp}"
                logger.warning("Gemini Live: {}", last_error)
                await ws.close()

            except asyncio.TimeoutError:
                last_error = f"Setup timed out for {model_name}"
                logger.warning("Gemini Live: {}", last_error)
                try:
                    await ws.close()
                except Exception:
                    pass
            except Exception as exc:
                last_error = f"{model_name}: {exc}"
                logger.warning("Gemini Live: setup failed for {}: {}", model_name, exc)
                try:
                    await ws.close()
                except Exception:
                    pass

        # All models failed
        logger.error("Gemini Live: all models failed. Last error: {}", last_error)
        self.session_error.emit(f"All models failed: {last_error}")

    async def send_audio(self, chunk: bytes) -> None:
        """Send a raw PCM audio chunk (16kHz 16-bit mono) to Gemini."""
        if not self._connected or not self._ws:
            return

        audio_b64 = base64.b64encode(chunk).decode("ascii")
        msg = {
            "realtimeInput": {
                "audio": {
                    "data": audio_b64,
                    "mimeType": "audio/pcm;rate=16000",
                }
            }
        }

        try:
            await self._ws.send(json.dumps(msg))
        except Exception as exc:
            logger.debug("Gemini Live: send_audio error: {}", exc)

    async def send_text(self, text: str) -> None:
        """Send a text message (e.g. user types instead of speaks)."""
        if not self._connected or not self._ws:
            return

        msg = {
            "clientContent": {
                "turns": [{"role": "user", "parts": [{"text": text}]}],
                "turnComplete": True,
            }
        }

        try:
            await self._ws.send(json.dumps(msg))
        except Exception:
            logger.debug("Gemini Live: send_text error")

    async def disconnect(self) -> None:
        """Close the WebSocket session."""
        self._connected = False

        if self._receive_task and not self._receive_task.done():
            self._receive_task.cancel()
            try:
                await self._receive_task
            except (asyncio.CancelledError, Exception):
                pass

        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None

        logger.info("Gemini Live: session disconnected")
        self.session_ended.emit()

    @property
    def is_connected(self) -> bool:
        return self._connected

    # ------------------------------------------------------------------
    # Internal — receive loop
    # ------------------------------------------------------------------

    async def _receive_loop(self) -> None:
        """Background task that processes incoming WebSocket messages."""
        try:
            async for raw_msg in self._ws:
                if not self._connected:
                    break
                try:
                    msg = json.loads(raw_msg)
                    self._handle_message(msg)
                except json.JSONDecodeError:
                    logger.debug("Gemini Live: non-JSON message received")
                except Exception as exc:
                    logger.debug("Gemini Live: message handling error: {}", exc)

        except asyncio.CancelledError:
            pass
        except Exception as exc:
            if self._connected:
                logger.error("Gemini Live: receive loop error: {}", exc)
                self.session_error.emit(f"Connection lost: {exc}")
        finally:
            self._connected = False
            self.session_ended.emit()

    def _handle_message(self, msg: dict) -> None:
        """Route an incoming Gemini Live message to the appropriate signal."""
        sc = msg.get("serverContent")
        if sc is None:
            # Could be toolCall, usageMetadata, goAway, etc.
            if "goAway" in msg:
                logger.warning("Gemini Live: server sent goAway — session ending")
                self.session_error.emit("Server ending session")
            return

        # Model audio/text response
        model_turn = sc.get("modelTurn")
        if model_turn:
            parts = model_turn.get("parts", [])
            for part in parts:
                inline = part.get("inlineData")
                if inline:
                    # Audio response chunk
                    audio_b64 = inline.get("data", "")
                    if audio_b64:
                        try:
                            audio_bytes = base64.b64decode(audio_b64)
                            self.audio_response.emit(audio_bytes)
                        except Exception:
                            pass

                text = part.get("text")
                if text:
                    self.text_response.emit(text)

        # Turn complete
        if sc.get("turnComplete"):
            self.turn_complete.emit()

        # Input transcription (what the user said)
        input_tx = sc.get("inputTranscription")
        if input_tx:
            text = input_tx.get("text", "").strip()
            if text:
                self.user_transcript.emit(text)
                logger.debug("Gemini Live: user said: '{}'", text[:80])

        # Output transcription (what the model said)
        output_tx = sc.get("outputTranscription")
        if output_tx:
            text = output_tx.get("text", "").strip()
            if text:
                self.text_response.emit(text)
                logger.debug("Gemini Live: model said: '{}'", text[:80])

        # Interrupted flag
        if sc.get("interrupted"):
            logger.debug("Gemini Live: model was interrupted by user")
