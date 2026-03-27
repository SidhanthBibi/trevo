"""Entry point for trevo — voice-to-text desktop application."""

from __future__ import annotations

import argparse
import asyncio
import signal
import sys
from pathlib import Path
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Bootstrap logging before anything else
# ---------------------------------------------------------------------------
from utils.logger import logger, setup_logger


# ---------------------------------------------------------------------------
# Single-instance guard
# ---------------------------------------------------------------------------

_LOCK_NAME = "trevo_single_instance"


def _acquire_single_instance() -> Any:
    """Prevent multiple trevo instances from running simultaneously.

    On Windows uses a named mutex; returns a handle that must be kept alive.
    On other platforms this is a no-op.
    """
    if sys.platform != "win32":
        return None
    try:
        import win32event  # type: ignore[import-not-found]
        import win32api  # type: ignore[import-not-found]
        import winerror  # type: ignore[import-not-found]

        mutex = win32event.CreateMutex(None, False, _LOCK_NAME)
        if win32api.GetLastError() == winerror.ERROR_ALREADY_EXISTS:
            logger.error("Another instance of trevo is already running. Exiting.")
            sys.exit(1)
        return mutex
    except ImportError:
        logger.debug("pywin32 not available — skipping single-instance check")
        return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    """Launch the trevo application."""

    # --- CLI arguments -------------------------------------------------------
    parser = argparse.ArgumentParser(
        prog="trevo",
        description="trevo — voice-to-text desktop application",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug-level logging to stderr",
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to a custom config.toml file",
    )
    args = parser.parse_args()

    # Reconfigure logger if --debug
    if args.debug:
        setup_logger(log_level="DEBUG")
        logger.debug("Debug logging enabled")

    # --- Single instance check -----------------------------------------------
    _mutex = _acquire_single_instance()  # noqa: F841  (must stay alive)

    # --- Load config ---------------------------------------------------------
    from models.settings import Settings

    if args.config:
        config_path = args.config
    elif hasattr(sys, '_MEIPASS'):
        # PyInstaller bundle — config next to the exe
        config_path = str(Path(sys.executable).parent / "config.toml")
    else:
        config_path = str(Path(__file__).resolve().parent / "config.toml")
    settings = Settings.load(config_path)

    # --- Qt application ------------------------------------------------------
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import QTimer

    app = QApplication(sys.argv)
    app.setApplicationName("trevo")
    app.setOrganizationName("trevo")
    app.setQuitOnLastWindowClosed(False)  # keep running in tray

    # Apply global theme
    from ui.styles import get_theme

    theme_name = settings.general.theme if settings.general.theme != "system" else "dark"
    try:
        app.setStyleSheet(get_theme(theme_name))
    except KeyError:
        app.setStyleSheet(get_theme("dark"))

    # --- Create core controller ----------------------------------------------
    from core.app import TrevoApp, AppState

    trevo = TrevoApp(settings=settings)

    # --- Create UI components ------------------------------------------------
    from ui.tray_icon import TrayIcon, TrayState
    from ui.dictation_bar import DictationBar
    from ui.settings_dialog import SettingsDialog
    from ui.transcript_viewer import TranscriptViewer

    # Dictation bar (floating overlay)
    dictation_bar = DictationBar()

    # System tray icon (the main visible component)
    tray = TrayIcon()

    # Trevo Mode
    from ui.trevo_mode import TrevoModeWindow
    trevo_mode = TrevoModeWindow()

    # Command Palette
    from ui.command_palette import CommandPalette
    command_palette = CommandPalette()

    # Toast Notifications
    from ui.toast import ToastManager, ToastType

    # Ambient Widget (always-on-top compact recording indicator)
    from ui.ambient_widget import AmbientWidget
    ambient_widget = AmbientWidget()
    ambient_widget.set_state("idle")

    # --- Wire trevo signals → UI ---------------------------------------------

    def _on_state_changed(state: AppState) -> None:
        """Update all UI elements when app state changes."""
        if state == AppState.RECORDING:
            tray.set_state(TrayState.RECORDING)
            dictation_bar.set_state("recording")
            dictation_bar.show_bar()
            ambient_widget.set_state("recording")
            ambient_widget.show()
        elif state == AppState.PROCESSING:
            tray.set_state(TrayState.PROCESSING)
            dictation_bar.set_state("processing")
            ambient_widget.set_state("processing")
        elif state == AppState.IDLE:
            tray.set_state(TrayState.IDLE)
            dictation_bar.set_state("idle")
            dictation_bar.hide_bar()
            ambient_widget.set_state("idle")
            ambient_widget.hide()

    trevo.state_changed.connect(_on_state_changed)

    # Live transcript preview in the bar + Trevo Mode overlay
    def _on_raw_transcript(text: str):
        dictation_bar.update_transcript(text)
        # Store user's speech for pairing with response in Trevo Mode
        if trevo_mode.isVisible() and text:
            trevo_mode.add_message(text, "user")

    trevo.raw_transcript_ready.connect(_on_raw_transcript)

    # Real-time interim transcript (words appear as you speak)
    def _on_interim_transcript(text: str):
        dictation_bar.update_transcript(text)

    trevo.interim_transcript_ready.connect(_on_interim_transcript)

    # Audio level meter
    trevo.audio_level_changed.connect(dictation_bar.update_audio_level)

    # Error notifications via toast (fallback to tray)
    def _on_error(msg: str) -> None:
        try:
            ToastManager.show("Error", msg, ToastType.ERROR)
        except Exception:
            tray.showMessage("trevo", msg, tray.MessageIcon.Warning, 3000)

    trevo.error_occurred.connect(_on_error)

    # --- Recording timer -----------------------------------------------------
    _recording_seconds = [0]
    _recording_timer = QTimer()
    _recording_timer.setInterval(1000)

    def _tick_timer() -> None:
        _recording_seconds[0] += 1
        dictation_bar.update_timer(_recording_seconds[0])

    _recording_timer.timeout.connect(_tick_timer)

    def _manage_timer(state: AppState) -> None:
        if state == AppState.RECORDING:
            _recording_seconds[0] = 0
            dictation_bar.update_timer(0)
            _recording_timer.start()
        else:
            _recording_timer.stop()

    trevo.state_changed.connect(_manage_timer)

    # --- Wire tray menu actions → app ----------------------------------------

    tray.dictation_requested.connect(
        lambda: trevo.start_recording()
        if trevo.state == AppState.IDLE
        else trevo.stop_recording()
    )

    def _open_settings() -> None:
        # Get the correct polish API key based on current provider
        polish_provider = settings.polishing.provider
        polish_key = ""
        if polish_provider == "openai":
            polish_key = settings.polishing.openai_api_key
        elif polish_provider == "anthropic":
            polish_key = settings.polishing.anthropic_api_key
        elif polish_provider == "groq":
            polish_key = settings.polishing.groq_api_key
        elif polish_provider == "gemini":
            polish_key = settings.polishing.gemini_api_key

        current = {
            # General
            "hotkey": settings.general.hotkey,
            "mode": settings.general.mode.title(),
            "auto_start": settings.general.auto_start,
            "theme": settings.general.theme.title(),
            # Speech Engine
            "stt_engine": settings.stt.engine,
            "groq_stt_api_key": settings.stt.groq_api_key,
            "gemini_stt_api_key": settings.stt.gemini_api_key,
            "google_cloud_stt_api_key": settings.stt.google_cloud_api_key,
            "openai_api_key": settings.stt.openai_api_key,
            "stt_language": settings.stt.language,
            # AI Polishing
            "polishing_enabled": settings.polishing.enabled,
            "polish_provider": polish_provider,
            "polish_api_key": polish_key,
            "context_aware": settings.polishing.context_aware,
            # Audio
            "input_device": settings.audio.input_device,
            "sample_rate": settings.audio.sample_rate,
            "noise_gate": int(settings.audio.noise_gate_threshold * 100),
            "vad_sensitivity": int(settings.audio.vad_sensitivity * 100),
            # Appearance
            "bar_position": settings.ui.bar_position.replace("_", " ").title(),
            "opacity": int(settings.ui.bar_opacity * 100),
            "font_size": settings.ui.font_size,
            "show_interim": settings.ui.show_interim_results,
            # History
            "history_enabled": settings.history.enabled,
            "max_entries": settings.history.max_entries,
            "auto_cleanup_days": settings.history.auto_cleanup_days,
            # Knowledge
            "vault_path": settings.knowledge.vault_path,
        }
        dlg = SettingsDialog(settings=current, parent=None)
        if dlg.exec():
            new_settings = dlg.get_settings()
            logger.info("Settings saved: {}", {k: "***" if "key" in k else v for k, v in new_settings.items()})
            try:
                # General
                settings.general.hotkey = new_settings.get("hotkey", settings.general.hotkey)
                settings.general.mode = new_settings.get("mode", "Toggle").lower()
                settings.general.auto_start = new_settings.get("auto_start", False)
                settings.general.theme = new_settings.get("theme", "Dark").lower()

                # Speech Engine
                settings.stt.engine = new_settings.get("stt_engine", settings.stt.engine)
                settings.stt.groq_api_key = new_settings.get("groq_stt_api_key", "")
                settings.stt.gemini_api_key = new_settings.get("gemini_stt_api_key", "")
                settings.stt.google_cloud_api_key = new_settings.get("google_cloud_stt_api_key", "")
                settings.stt.openai_api_key = new_settings.get("openai_api_key", "")
                settings.stt.language = new_settings.get("stt_language", "en")

                # AI Polishing
                settings.polishing.enabled = new_settings.get("polishing_enabled", True)
                settings.polishing.provider = new_settings.get("polish_provider", "groq")
                settings.polishing.context_aware = new_settings.get("context_aware", True)
                # Route the polish API key to the correct provider field
                p_key = new_settings.get("polish_api_key", "")
                p_provider = new_settings.get("polish_provider", "groq")
                if p_provider == "openai":
                    settings.polishing.openai_api_key = p_key
                elif p_provider == "anthropic":
                    settings.polishing.anthropic_api_key = p_key
                elif p_provider == "groq":
                    settings.polishing.groq_api_key = p_key
                elif p_provider == "gemini":
                    settings.polishing.gemini_api_key = p_key

                # Audio
                settings.audio.sample_rate = new_settings.get("sample_rate", 16000)
                settings.audio.noise_gate_threshold = new_settings.get("noise_gate", 20) / 100.0
                settings.audio.vad_sensitivity = new_settings.get("vad_sensitivity", 50) / 100.0

                # Appearance
                bar_pos = new_settings.get("bar_position", "Top Center")
                settings.ui.bar_position = bar_pos.lower().replace(" ", "_")
                settings.ui.bar_opacity = new_settings.get("opacity", 90) / 100.0
                settings.ui.font_size = new_settings.get("font_size", 14)
                settings.ui.show_interim_results = new_settings.get("show_interim", True)

                # History
                settings.history.enabled = new_settings.get("history_enabled", True)
                settings.history.max_entries = new_settings.get("max_entries", 10000)
                settings.history.auto_cleanup_days = new_settings.get("auto_cleanup_days", 90)

                # Knowledge
                settings.knowledge.vault_path = new_settings.get("vault_path", "")

                settings.save(config_path)
            except Exception:
                logger.exception("Failed to persist settings")

    tray.settings_requested.connect(_open_settings)

    def _open_history() -> None:
        viewer = TranscriptViewer(parent=None)
        # Load entries from database if available
        if trevo._database is not None:
            try:
                from ui.transcript_viewer import TranscriptEntry

                rows = trevo._database.get_all_transcripts()
                entries = []
                for row in rows:
                    entries.append(TranscriptEntry(
                        id=str(row.id) if row.id else "",
                        timestamp=row.created_at,
                        raw_text=row.raw_text,
                        polished_text=row.polished_text,
                        language=row.language,
                        app_context=str(row.app_context) if row.app_context else "",
                        duration_seconds=row.duration_seconds or 0.0,
                    ))
                viewer.set_entries(entries)
            except Exception:
                logger.exception("Failed to load transcript history")
        viewer.exec()

    tray.history_requested.connect(_open_history)

    # Knowledge vault — open in file explorer
    def _open_knowledge() -> None:
        import subprocess
        vault_path = trevo._knowledge.vault_path
        if sys.platform == "win32":
            subprocess.Popen(["explorer", str(vault_path)])
        else:
            subprocess.Popen(["xdg-open", str(vault_path)])

    tray.knowledge_requested.connect(_open_knowledge)

    # --- Gemini Live session for Trevo Mode (real-time bidirectional voice) ---
    from core.gemini_live import GeminiLiveSession
    from core.audio_playback import AudioPlayer

    _gemini_session: list[Optional[GeminiLiveSession]] = [None]  # mutable container
    _gemini_audio_handler: list[object] = [None]  # named ref for clean disconnect
    _audio_player = AudioPlayer()

    def _start_gemini_live():
        """Start a Gemini Live session for real-time voice conversation."""
        gemini_key = settings.stt.gemini_api_key or settings.polishing.gemini_api_key
        if not gemini_key:
            logger.warning("Gemini Live: no API key configured, falling back to legacy mode")
            return False

        # Build system prompt with snippets
        system_prompt = (
            "You are Trevo, a helpful AI voice assistant running on the user's "
            "Windows desktop. You speak naturally and conversationally. "
            "Keep responses concise (1-3 sentences) unless asked for detail."
        )
        if settings.snippets:
            snippet_lines = "\n".join(
                f"- {k.replace('_', ' ')}: {v}" for k, v in settings.snippets.items() if v
            )
            if snippet_lines:
                system_prompt += (
                    f"\n\nUser's personal info:\n{snippet_lines}\n"
                    "Use these exact values when the user refers to them."
                )

        session = GeminiLiveSession(
            api_key=gemini_key,
            system_prompt=system_prompt,
            voice="Kore",
        )
        _gemini_session[0] = session

        # Wire signals
        session.audio_response.connect(_audio_player.play_chunk)
        session.text_response.connect(lambda t: trevo_mode.add_message(t, "trevo") if trevo_mode.isVisible() else None)
        session.user_transcript.connect(lambda t: trevo_mode.add_message(t, "user") if trevo_mode.isVisible() else None)

        from ui.trevo_mode import TrevoState

        # Define mic→Gemini handler (but don't connect until session is ready)
        def _send_to_gemini(chunk: bytes):
            s = _gemini_session[0]
            if s and s.is_connected:
                asyncio.run_coroutine_threadsafe(s.send_audio(chunk), trevo._loop)

        _gemini_audio_handler[0] = _send_to_gemini

        def _on_session_started():
            logger.info("Gemini Live: session started — starting mic capture")
            trevo_mode.set_state(TrevoState.LISTENING)
            # NOW start mic — only after WebSocket is ready
            trevo._audio_capture.audio_chunk.connect(_send_to_gemini)
            trevo._audio_capture.start()

        session.session_started.connect(_on_session_started)
        session.turn_complete.connect(lambda: (
            trevo_mode.set_state(TrevoState.LISTENING) if trevo_mode.isVisible() else None
        ))
        session.session_error.connect(lambda msg: (
            logger.error("Gemini Live error: {}", msg),
            trevo.error_occurred.emit(f"Gemini Live: {msg}"),
        ))
        session.session_ended.connect(lambda: logger.info("Gemini Live: session ended"))

        # Track audio response for sphere state
        session.audio_response.connect(
            lambda _: trevo_mode.set_state(TrevoState.SPEAKING) if trevo_mode.isVisible() else None
        )

        # Start audio player (output stream ready for responses)
        _audio_player.start()

        # Show connecting state while WebSocket handshakes
        trevo_mode.set_state(TrevoState.PROCESSING)

        # Connect to Gemini Live WebSocket (mic starts in _on_session_started)
        asyncio.run_coroutine_threadsafe(session.connect(), trevo._loop)
        return True

    def _stop_gemini_live():
        """Stop the Gemini Live session and clean up."""
        session = _gemini_session[0]
        if session:
            asyncio.run_coroutine_threadsafe(session.disconnect(), trevo._loop)
            _gemini_session[0] = None

        # Disconnect mic→Gemini handler
        handler = _gemini_audio_handler[0]
        if handler:
            try:
                trevo._audio_capture.audio_chunk.disconnect(handler)
            except (TypeError, RuntimeError):
                pass
            _gemini_audio_handler[0] = None

        _audio_player.stop()
        _audio_player.clear()
        trevo._audio_capture.stop()

    # Trevo Mode toggle — starts real-time voice via Gemini Live
    _trevo_using_gemini = [False]

    def _toggle_trevo_mode():
        if trevo_mode.isVisible():
            trevo_mode.hide_sphere()
            trevo._conversation.trevo_mode = False
            if _trevo_using_gemini[0]:
                _stop_gemini_live()
                _trevo_using_gemini[0] = False
            elif trevo.state == AppState.RECORDING:
                trevo.stop_recording()
        else:
            trevo_mode.show_sphere()
            trevo._conversation.trevo_mode = True
            # Try Gemini Live first, fall back to legacy mode
            if _start_gemini_live():
                _trevo_using_gemini[0] = True
                logger.info("Trevo Mode: using Gemini Live (real-time voice)")
            else:
                _trevo_using_gemini[0] = False
                if trevo.state == AppState.IDLE:
                    trevo.start_recording()
                logger.info("Trevo Mode: using legacy mode (record→process→speak)")

    tray.trevo_mode_requested.connect(_toggle_trevo_mode)
    trevo._hotkey_manager.trevo_mode.connect(_toggle_trevo_mode)

    # --- Escape / Cancel handling -----------------------------------------
    def _on_cancelled():
        """Dismiss active overlays and stop recording on Escape."""
        # Hide command palette if visible
        if command_palette.isVisible():
            command_palette.hide()
        # Hide Trevo Mode if visible
        if trevo_mode.isVisible():
            trevo_mode.hide_sphere()
            trevo._conversation.trevo_mode = False
            if _trevo_using_gemini[0]:
                _stop_gemini_live()
                _trevo_using_gemini[0] = False
            elif trevo.state == AppState.RECORDING:
                trevo.stop_recording()
        # Stop dictation if active
        if trevo.state == AppState.RECORDING:
            trevo.stop_recording()
        dictation_bar.hide_bar()

    trevo._hotkey_manager.cancelled.connect(_on_cancelled)

    # --- TTS voice responses (Trevo Mode speaks back) --------------------
    def _on_voice_response(text: str):
        if not text:
            return
        from ui.trevo_mode import TrevoState
        if trevo_mode.isVisible():
            trevo_mode.set_state(TrevoState.SPEAKING)
            # Show response in temporary overlay (pairs with last user text)
            trevo_mode.add_message(text, "trevo")

        def _speak():
            try:
                logger.info("TTS speaking: '{}'", text[:80])
                trevo._tts.speak_sync(text)
            except Exception:
                logger.exception("TTS failed for text: '{}'", text[:80])
            finally:
                # After speaking, go back to listening if Trevo Mode is active
                if trevo_mode.isVisible():
                    from PyQt6.QtCore import QTimer
                    QTimer.singleShot(0, lambda: trevo_mode.set_state(TrevoState.LISTENING))
                    # Auto-restart recording for continuous conversation
                    if trevo.state == AppState.IDLE:
                        QTimer.singleShot(200, trevo.start_recording)

        import threading
        threading.Thread(target=_speak, daemon=True, name="trevo-tts").start()

    trevo.voice_response_ready.connect(_on_voice_response)

    # --- Desktop automation via voice commands (routed through Agent Mode) ---
    def _on_desktop_command(command_text: str):
        async def _run_agent():
            try:
                result = await trevo._agent.process_agent_command(command_text)
                if result.action == "inject_text" and result.text:
                    from PyQt6.QtCore import QMetaObject, Qt, Q_ARG
                    QMetaObject.invokeMethod(
                        trevo, "transcript_ready", Qt.ConnectionType.QueuedConnection,
                        Q_ARG(str, result.text),
                    )
                elif result.action == "execute" and result.text:
                    if trevo_mode.isVisible():
                        trevo.voice_response_ready.emit(result.text)
                elif result.action == "confirm" and result.text:
                    if trevo_mode.isVisible():
                        trevo.voice_response_ready.emit(result.text)
                elif result.action == "error" and result.error:
                    trevo.error_occurred.emit(result.error)
                else:
                    # Fallback: speak any text result in Trevo Mode
                    if result.text and trevo_mode.isVisible():
                        trevo.voice_response_ready.emit(result.text)
            except Exception:
                logger.exception("Agent command failed: {}", command_text)
                trevo.error_occurred.emit(f"Failed: {command_text}")

        asyncio.run_coroutine_threadsafe(_run_agent(), trevo._loop)

    trevo.desktop_command_ready.connect(_on_desktop_command)

    # Workflow Editor
    def _open_workflow_editor():
        from ui.workflow_editor import WorkflowEditorDialog
        editor = WorkflowEditorDialog(parent=None)
        editor.exec()

    tray.workflow_editor_requested.connect(_open_workflow_editor)

    # --- Command Palette -----------------------------------------------
    def _on_palette_action(action_id: str):
        logger.debug("Command palette action: {}", action_id)
        if action_id == "start_dictation":
            if trevo.state == AppState.IDLE:
                trevo.start_recording()
            else:
                trevo.stop_recording()
        elif action_id == "toggle_trevo_mode":
            _toggle_trevo_mode()
        elif action_id == "open_settings":
            _open_settings()
        elif action_id == "view_history":
            _open_history()
        elif action_id == "open_workflow_editor":
            _open_workflow_editor()
        elif action_id == "toggle_theme":
            current = settings.general.theme
            new_theme = "light" if current == "dark" else "dark"
            settings.general.theme = new_theme
            try:
                app.setStyleSheet(get_theme(new_theme))
            except KeyError:
                pass
        elif action_id == "quit_trevo":
            _quit()

    command_palette.action_triggered.connect(_on_palette_action)
    trevo._hotkey_manager.command_palette.connect(command_palette.toggle)

    # --- Text input from Trevo Mode (signal kept for compatibility) ------
    # Chat box removed — Trevo Mode is now sphere-only with voice interaction

    # Clap detection → toggle Trevo Mode (only if openwakeword/deps available)
    clap_detector = None
    try:
        from core.clap_detector import ClapDetector
        clap_detector = ClapDetector()
        if settings.general.clap_detection_enabled:
            clap_detector.clap_detected.connect(_toggle_trevo_mode)
    except Exception:
        logger.debug("Clap detection not available (missing deps)")

    # Wake word detection → toggle Trevo Mode (only if openwakeword available)
    wake_word = None
    try:
        from core.wake_word import WakeWordDetector
        wake_word = WakeWordDetector(threshold=0.5, cooldown_seconds=3.0)
        if settings.general.wake_word_enabled:
            wake_word.start()
            wake_word.wake_word_detected.connect(_toggle_trevo_mode)
    except Exception:
        logger.debug("Wake word detection not available (missing deps)")

    # Connect audio detectors to audio stream
    if trevo._audio_capture is not None:
        if clap_detector is not None and settings.general.clap_detection_enabled:
            trevo._audio_capture.audio_chunk.connect(clap_detector.process_audio)
        if wake_word is not None and settings.general.wake_word_enabled:
            trevo._audio_capture.audio_chunk.connect(wake_word.process_audio)

    # When app state changes, update Trevo Mode sphere if visible
    from ui.trevo_mode import TrevoState

    def _update_trevo_state(state: AppState):
        if trevo_mode.isVisible():
            # Skip state updates when using Gemini Live (it manages its own states)
            if _trevo_using_gemini[0]:
                return

            state_map = {
                AppState.IDLE: TrevoState.IDLE,
                AppState.RECORDING: TrevoState.LISTENING,
                AppState.PROCESSING: TrevoState.PROCESSING,
            }
            trevo_mode.set_state(state_map.get(state, TrevoState.IDLE))

            # In legacy Trevo Mode, auto-restart recording after processing
            if state == AppState.IDLE:
                QTimer.singleShot(500, lambda: (
                    trevo.start_recording()
                    if trevo_mode.isVisible() and trevo.state == AppState.IDLE
                    and not _trevo_using_gemini[0]
                    else None
                ))

    trevo.state_changed.connect(_update_trevo_state)

    # Morning briefing handler
    def _on_conversation_message(msg: str):
        if msg == "morning_briefing":
            trevo_mode.show_sphere()
            trevo_mode.set_state(TrevoState.PROCESSING)

            from core.morning_briefing import fetch_morning_briefing

            async def _run_briefing():
                try:
                    text = await fetch_morning_briefing(name="Sidhanth")
                    trevo.voice_response_ready.emit(text)
                except Exception:
                    logger.exception("Morning briefing failed")
                    trevo.voice_response_ready.emit(
                        "Good morning! Sorry, I had trouble fetching today's briefing."
                    )

            asyncio.run_coroutine_threadsafe(_run_briefing(), trevo._loop)

    trevo.conversation_message.connect(_on_conversation_message)

    # Dictation bar close button
    dictation_bar.close_requested.connect(
        lambda: trevo.stop_recording() if trevo.state == AppState.RECORDING else None
    )

    # Quit
    def _quit() -> None:
        logger.info("Quit requested")
        trevo_mode.close()
        trevo.shutdown()
        app.quit()

    tray.quit_requested.connect(_quit)

    # --- Tray status info ----------------------------------------------------
    engine_name = settings.stt.engine
    tray.set_engine_status(engine_name)
    lang = settings.stt.language
    tray.set_language_status(lang)

    # --- Show tray -----------------------------------------------------------
    tray.show()

    # --- OS signal handling --------------------------------------------------
    signal.signal(signal.SIGINT, lambda *_: _quit())
    signal.signal(signal.SIGTERM, lambda *_: _quit())

    # Timer trick: periodically return control to Python so signals are handled.
    _signal_timer = QTimer()
    _signal_timer.timeout.connect(lambda: None)
    _signal_timer.start(200)

    logger.info("trevo is running. RCtrl: 2x=dictation, 3x=palette, 4x=Trevo. Escape=dismiss.")

    # --- Enter Qt event loop -------------------------------------------------
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
