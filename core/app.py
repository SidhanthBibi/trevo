"""Main application controller for trevo.

Owns all core components and orchestrates the voice-to-text pipeline:
hotkey → audio capture → VAD → STT → polish → inject.
"""

from __future__ import annotations

import asyncio
import enum
import threading
from typing import Optional

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot

from core.command_parser import CommandParser, CommandResult, CommandType
from core.conversation_engine import ConversationEngine, ConversationResult, Intent
from core.hotkey_manager import DictationMode, HotkeyManager
from core.language_manager import LanguageManager
from core.text_injector import TextInjector
from models.settings import Settings
from knowledge.graph import KnowledgeGraph
from storage.database import DatabaseManager
from utils.logger import logger


class AppState(enum.Enum):
    """State machine states for the trevo pipeline."""

    IDLE = "idle"
    RECORDING = "recording"
    PROCESSING = "processing"
    COMMAND_MODE = "command_mode"


class TrevoApp(QObject):
    """Central application controller (singleton).

    Owns every core component and wires their signals together.
    An asyncio event loop runs in a background thread so that async
    STT and polishing calls never block the Qt event loop.
    """

    # Singleton ----------------------------------------------------------------
    _instance: Optional[TrevoApp] = None

    @classmethod
    def instance(cls) -> Optional[TrevoApp]:
        return cls._instance

    # Signals ------------------------------------------------------------------
    state_changed = pyqtSignal(AppState)       # emits AppState enum directly
    transcript_ready = pyqtSignal(str)         # polished (or raw) text
    raw_transcript_ready = pyqtSignal(str)     # unpolished STT output
    conversation_message = pyqtSignal(str)     # status from conversation engine
    error_occurred = pyqtSignal(str)           # human-readable error message
    audio_level_changed = pyqtSignal(float)    # 0.0 – 1.0

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def __init__(self, settings: Settings, parent: Optional[QObject] = None) -> None:
        if TrevoApp._instance is not None:
            raise RuntimeError("TrevoApp is a singleton — use TrevoApp.instance()")
        super().__init__(parent)
        TrevoApp._instance = self

        self._settings = settings
        self._state = AppState.IDLE

        # Async loop running on a daemon thread
        self._loop = asyncio.new_event_loop()
        self._loop_thread = threading.Thread(
            target=self._run_loop, daemon=True, name="trevo-async-loop",
        )

        # Core components (created in _init_components)
        self._hotkey_manager: HotkeyManager = None  # type: ignore[assignment]
        self._audio_capture: QObject = None  # type: ignore[assignment]
        self._vad: QObject = None  # type: ignore[assignment]
        self._stt_engine: object = None  # type: ignore[assignment]
        self._text_polisher: object = None  # type: ignore[assignment]
        self._text_injector: TextInjector = None  # type: ignore[assignment]
        self._context_detector: object = None  # type: ignore[assignment]
        self._command_parser: CommandParser = None  # type: ignore[assignment]
        self._conversation: ConversationEngine = None  # type: ignore[assignment]
        self._language_manager: LanguageManager = None  # type: ignore[assignment]
        self._database: DatabaseManager = None  # type: ignore[assignment]
        self._knowledge: KnowledgeGraph = None  # type: ignore[assignment]

        # Initialise everything
        self._init_components()
        self._wire_signals()
        self._loop_thread.start()

        logger.info("TrevoApp initialised (state={})", self._state.value)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def state(self) -> AppState:
        return self._state

    @property
    def settings(self) -> Settings:
        return self._settings

    # ------------------------------------------------------------------
    # Component initialisation
    # ------------------------------------------------------------------

    def _init_components(self) -> None:
        """Create all core components from the loaded settings."""

        # --- Audio Capture ---------------------------------------------------
        from core.audio_capture import AudioCapture

        device: Optional[int] = None
        raw_device = self._settings.audio.input_device
        if raw_device not in (None, "default", ""):
            try:
                device = int(raw_device)
            except (ValueError, TypeError):
                device = None

        self._audio_capture = AudioCapture(
            device=device,
            noise_gate_threshold=self._settings.audio.noise_gate_threshold,
        )

        # --- VAD -------------------------------------------------------------
        from core.vad import VoiceActivityDetector

        self._vad = VoiceActivityDetector(
            sample_rate=self._settings.audio.sample_rate,
            silence_threshold_s=self._settings.audio.vad_sensitivity,
        )

        # --- STT Engine ------------------------------------------------------
        self._stt_engine = self._create_stt_engine()

        # --- Context Detector ------------------------------------------------
        from core.context_detector import ContextDetector

        self._context_detector = ContextDetector()

        # --- Text Polisher ---------------------------------------------------
        from core.text_polisher import TextPolisher

        provider = self._settings.polishing.provider
        api_key: Optional[str] = None
        if provider == "openai":
            api_key = self._settings.polishing.openai_api_key or self._settings.stt.openai_api_key
        elif provider == "anthropic":
            api_key = self._settings.polishing.anthropic_api_key

        self._text_polisher = TextPolisher(
            provider=provider if provider != "none" else "openai",
            api_key=api_key or None,
            model=None,
            ollama_base_url=self._settings.polishing.ollama_url,
        )
        self._polishing_enabled = self._settings.polishing.enabled and provider != "none"

        # --- Text Injector (real module with clipboard save/restore) ----------
        self._text_injector = TextInjector()

        # --- Command Parser --------------------------------------------------
        self._command_parser = CommandParser()

        # --- Conversation Engine (the brain) ---------------------------------
        conv_provider = self._settings.polishing.provider
        conv_key: Optional[str] = None
        if conv_provider == "openai":
            conv_key = self._settings.polishing.openai_api_key or self._settings.stt.openai_api_key
        elif conv_provider == "anthropic":
            conv_key = self._settings.polishing.anthropic_api_key
        elif conv_provider == "groq":
            conv_key = self._settings.polishing.groq_api_key
        elif conv_provider == "gemini":
            conv_key = self._settings.polishing.gemini_api_key
        self._conversation = ConversationEngine(
            provider=conv_provider if conv_provider != "none" else "ollama",
            api_key=conv_key or None,
            model=None,  # use defaults
            ollama_url=self._settings.polishing.ollama_url,
        )

        # --- Language Manager ------------------------------------------------
        lang = self._settings.stt.language
        self._language_manager = LanguageManager(
            language=None if lang == "auto" else lang,
        )

        # --- Hotkey Manager --------------------------------------------------
        mode_str = self._settings.general.mode
        dictation_mode = (
            DictationMode.PUSH_TO_TALK
            if mode_str == "push_to_talk"
            else DictationMode.TOGGLE
        )
        self._hotkey_manager = HotkeyManager(mode=dictation_mode)
        self._hotkey_manager.start()

        # --- Database / History ----------------------------------------------
        if self._settings.history.enabled:
            self._database = DatabaseManager()
        else:
            self._database = None  # type: ignore[assignment]

        # --- Knowledge Graph (Obsidian-style vault) --------------------------
        self._knowledge = KnowledgeGraph()

        logger.info("All components initialised")

    def _create_stt_engine(self) -> object:
        """Instantiate the configured STT engine."""
        engine_name = self._settings.stt.engine

        if engine_name == "whisper_local":
            from core.stt_whisper import WhisperLocalSTT

            return WhisperLocalSTT(
                model_size=self._settings.stt.whisper.model_size,
                device=self._settings.stt.whisper.device,
                compute_type=self._settings.stt.whisper.compute_type,
            )

        if engine_name == "openai":
            from core.stt_openai import OpenAISTT

            return OpenAISTT(api_key=self._settings.stt.openai_api_key)

        if engine_name == "groq":
            from core.stt_groq import GroqSTT

            groq_key = self._settings.stt.groq_api_key or self._settings.polishing.groq_api_key
            return GroqSTT(api_key=groq_key)

        if engine_name == "gemini":
            from core.stt_gemini import GeminiSTT
            gemini_key = self._settings.polishing.gemini_api_key or self._settings.stt.gemini_api_key
            return GeminiSTT(api_key=gemini_key)

        if engine_name == "google_cloud":
            from core.stt_google import GoogleCloudSTT
            return GoogleCloudSTT(api_key=self._settings.stt.google_cloud_api_key)

        # Default / deepgram
        try:
            from core.stt_deepgram import DeepgramSTT  # type: ignore[import-not-found]

            return DeepgramSTT(api_key=self._settings.stt.deepgram_api_key)
        except ImportError:
            logger.warning(
                "Deepgram STT module not found; falling back to whisper_local",
            )
            from core.stt_whisper import WhisperLocalSTT

            return WhisperLocalSTT()

    # ------------------------------------------------------------------
    # Signal wiring
    # ------------------------------------------------------------------

    def _wire_signals(self) -> None:
        """Connect Qt signals between components."""
        # Audio level passthrough
        self._audio_capture.audio_level.connect(self.audio_level_changed)

        # Audio chunks → VAD
        self._audio_capture.audio_chunk.connect(self._on_audio_chunk)

        # VAD speech boundaries
        self._vad.speech_start.connect(self._on_speech_start)
        self._vad.speech_end.connect(self._on_speech_end)

        # Hotkey events — real HotkeyManager signals
        self._hotkey_manager.dictation_toggled.connect(self._on_dictation_toggled)
        self._hotkey_manager.command_mode.connect(self._on_command_mode)
        self._hotkey_manager.mute_toggled.connect(self._on_mute_toggled)
        self._hotkey_manager.cancelled.connect(self._on_cancelled)

    # ------------------------------------------------------------------
    # Async event loop
    # ------------------------------------------------------------------

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def _run_async(self, coro: object) -> asyncio.Future:
        """Schedule a coroutine on the background loop and return its Future."""
        return asyncio.run_coroutine_threadsafe(coro, self._loop)  # type: ignore[arg-type]

    # ------------------------------------------------------------------
    # State machine
    # ------------------------------------------------------------------

    def _set_state(self, new_state: AppState) -> None:
        if new_state == self._state:
            return
        old = self._state
        self._state = new_state
        logger.info("State: {} → {}", old.value, new_state.value)
        self.state_changed.emit(new_state)

    # ------------------------------------------------------------------
    # Hotkey handlers
    # ------------------------------------------------------------------

    @pyqtSlot(bool)
    def _on_dictation_toggled(self, active: bool) -> None:
        """Handle dictation toggle from HotkeyManager."""
        if active:
            if self._state == AppState.IDLE:
                self.start_recording()
        else:
            if self._state == AppState.RECORDING:
                self.stop_recording()

    @pyqtSlot()
    def _on_command_mode(self) -> None:
        """Handle command mode activation from HotkeyManager."""
        if self._state == AppState.IDLE:
            self._set_state(AppState.COMMAND_MODE)
            self._audio_capture.start()
        elif self._state == AppState.COMMAND_MODE:
            self._audio_capture.stop()
            self._vad.reset()
            self._set_state(AppState.IDLE)

    @pyqtSlot()
    def _on_mute_toggled(self) -> None:
        """Handle mute toggle — stop recording without processing."""
        if self._state == AppState.RECORDING:
            self._audio_capture.stop()
            self._vad.reset()
            self._set_state(AppState.IDLE)
            logger.info("Recording muted / discarded")

    @pyqtSlot()
    def _on_cancelled(self) -> None:
        """Handle cancel — stop any active operation and return to idle."""
        if self._state == AppState.RECORDING:
            self._audio_capture.stop()
            self._vad.reset()
            self._set_state(AppState.IDLE)
            logger.info("Recording cancelled")
        elif self._state == AppState.COMMAND_MODE:
            self._audio_capture.stop()
            self._vad.reset()
            self._set_state(AppState.IDLE)
            logger.info("Command mode cancelled")

    # ------------------------------------------------------------------
    # Recording lifecycle
    # ------------------------------------------------------------------

    def start_recording(self) -> None:
        """Begin voice capture."""
        if self._state not in (AppState.IDLE,):
            logger.warning("Cannot start recording from state {}", self._state.value)
            return

        self._set_state(AppState.RECORDING)
        self._vad.reset()

        # Start the STT stream asynchronously
        self._run_async(self._stt_engine.start_stream())
        self._audio_capture.start()
        logger.info("Recording started")

    def stop_recording(self) -> None:
        """Stop voice capture and process any remaining audio."""
        if self._state != AppState.RECORDING:
            return

        self._audio_capture.stop()
        self._set_state(AppState.PROCESSING)

        # Flush: stop STT stream and collect final transcript
        future = self._run_async(self._finalize_transcript())
        future.add_done_callback(self._on_finalize_done)

    # ------------------------------------------------------------------
    # Audio / VAD pipeline
    # ------------------------------------------------------------------

    @pyqtSlot(bytes)
    def _on_audio_chunk(self, chunk: bytes) -> None:
        """Feed audio chunk to VAD and forward to STT engine."""
        segment = self._vad.process_chunk(chunk)

        if self._state == AppState.RECORDING:
            # Stream audio to STT in real time
            self._run_async(self._stt_engine.send_audio(chunk))

        if segment is not None:
            # A complete speech segment ended — could trigger batch STT
            if self._state == AppState.COMMAND_MODE:
                self._run_async(self._handle_command_segment(segment))

    @pyqtSlot()
    def _on_speech_start(self) -> None:
        logger.debug("VAD: speech started")

    @pyqtSlot()
    def _on_speech_end(self) -> None:
        logger.debug("VAD: speech ended")

    # ------------------------------------------------------------------
    # Transcript finalisation
    # ------------------------------------------------------------------

    async def _finalize_transcript(self) -> Optional[str]:
        """Stop the STT stream, collect text, route through conversation engine."""
        try:
            raw_text = ""
            async for event in self._stt_engine.get_transcripts():
                if event.is_final:
                    raw_text += event.text + " "

            await self._stt_engine.stop_stream()
            raw_text = raw_text.strip()

            if not raw_text:
                logger.info("No speech detected")
                return None

            self.raw_transcript_ready.emit(raw_text)
            logger.info("Raw transcript: '{}'", raw_text[:120])

            # Route through conversation engine — it handles intent detection,
            # polishing, transformation, replace, undo, everything.
            ctx = self._context_detector.get_active_context()
            result: ConversationResult = await self._conversation.process_speech(
                raw_text, app_context=ctx.app_type,
            )

            logger.info(
                "Conversation result: action={}, intent={}, msg='{}'",
                result.action, result.intent.value, result.message,
            )

            # Emit status message for the UI
            if result.message:
                self.conversation_message.emit(result.message)

            # Execute the result action
            if result.action == "inject_text" and result.text:
                self._text_injector.inject(result.text)
                self.transcript_ready.emit(result.text)
                self._command_parser.push_history(result.text)
                self._save_to_history(raw_text, result.text)

            elif result.action == "replace_all" and result.text:
                # Select all in active field, then paste replacement
                import pyautogui
                pyautogui.hotkey("ctrl", "a")
                await asyncio.sleep(0.05)
                self._text_injector.inject(result.text)
                self.transcript_ready.emit(result.text)
                self._command_parser.push_history(result.text)
                self._save_to_history(raw_text, result.text)

            elif result.action == "read_back":
                # Show the text in the UI (future: TTS)
                self.transcript_ready.emit(result.text)

            elif result.action == "clear":
                # Select all and delete
                import pyautogui
                pyautogui.hotkey("ctrl", "a")
                await asyncio.sleep(0.05)
                pyautogui.press("delete")

            # noop — do nothing

            return result.text or None

        except Exception:
            logger.exception("Error finalising transcript")
            self.error_occurred.emit("Failed to process voice input")
            return None

    def _on_finalize_done(self, future: asyncio.Future) -> None:
        """Callback when transcript finalisation completes."""
        try:
            future.result()
        except Exception:
            logger.exception("Finalize future raised")
            self.error_occurred.emit("Failed to process voice input")
        finally:
            self._set_state(AppState.IDLE)

    # ------------------------------------------------------------------
    # Command mode
    # ------------------------------------------------------------------

    async def _handle_command_segment(self, segment: object) -> None:
        """Transcribe a segment and treat the text as a command."""
        try:
            await self._stt_engine.start_stream()
            await self._stt_engine.send_audio(segment.audio)  # type: ignore[attr-defined]
            text = ""
            async for event in self._stt_engine.get_transcripts():
                if event.is_final:
                    text += event.text + " "
            await self._stt_engine.stop_stream()

            text = text.strip()
            if text:
                logger.info("Command: '{}'", text)
                result: CommandResult = self._command_parser.parse(text)
                self._execute_command_result(result)
        except Exception:
            logger.exception("Command handling failed")

    def _execute_command_result(self, result: CommandResult) -> None:
        """Execute a parsed CommandResult."""
        if result.command_type == CommandType.NONE:
            # Plain text — just inject it
            if result.remaining_text:
                self._text_injector.inject(result.remaining_text)
            return

        if result.command_type == CommandType.DICTATION:
            # Dictation command (punctuation, newlines, etc.) — inject expanded text
            expanded = result.parameters.get("expanded", "")
            if expanded:
                self._text_injector.inject(expanded)
            return

        if result.command_type == CommandType.EDIT:
            action = result.action
            if action == "undo":
                previous = result.parameters.get("previous_text")
                if previous is not None:
                    self._text_injector.inject(previous)
                    logger.info("Undo: restored previous text")
                else:
                    logger.info("Undo: no history available")
            else:
                # Other edit commands (make_formal, fix_grammar, translate, etc.)
                # would be handled by a future edit pipeline
                logger.info(
                    "Edit command '{}' with params {} — not yet implemented",
                    action,
                    result.parameters,
                )

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    def _save_to_history(self, raw_text: str, polished_text: str) -> None:
        """Persist transcript to the history database and knowledge graph."""
        # Save to SQLite history
        if self._database is not None:
            try:
                from models.transcript import Transcript
                from utils.text_utils import word_count

                record = Transcript(
                    raw_text=raw_text,
                    polished_text=polished_text,
                    word_count=word_count(polished_text),
                )
                self._database.insert_transcript(record)
                logger.debug("Saved transcript {} to history", record.id)
            except Exception:
                logger.exception("Failed to save transcript to history")

        # Save to knowledge graph (Obsidian-style .md vault)
        if self._knowledge is not None:
            try:
                ctx = self._context_detector.get_active_context()
                note = self._knowledge.create_from_dictation(
                    raw_text=raw_text,
                    polished_text=polished_text,
                    app_context=ctx.app_type,
                    auto_link=True,
                )
                logger.debug("Created knowledge note: '{}'", note.title)
            except Exception:
                logger.exception("Failed to save to knowledge graph")

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def shutdown(self) -> None:
        """Gracefully shut down all components."""
        logger.info("Shutting down TrevoApp")

        if self._state == AppState.RECORDING:
            self._audio_capture.stop()

        self._hotkey_manager.stop()

        # Stop async loop
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._loop_thread.join(timeout=3.0)

        TrevoApp._instance = None
        logger.info("TrevoApp shutdown complete")
