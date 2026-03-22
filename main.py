"""Entry point for trevo — voice-to-text desktop application."""

from __future__ import annotations

import argparse
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

    config_path = args.config or str(Path(__file__).resolve().parent / "config.toml")
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

    # --- Wire trevo signals → UI ---------------------------------------------

    def _on_state_changed(state: AppState) -> None:
        """Update all UI elements when app state changes."""
        if state == AppState.RECORDING:
            tray.set_state(TrayState.RECORDING)
            dictation_bar.set_state("recording")
            dictation_bar.show_bar()
        elif state == AppState.PROCESSING:
            tray.set_state(TrayState.PROCESSING)
            dictation_bar.set_state("processing")
        elif state == AppState.IDLE:
            tray.set_state(TrayState.IDLE)
            dictation_bar.set_state("idle")
            dictation_bar.hide_bar()
        elif state == AppState.COMMAND_MODE:
            tray.set_state(TrayState.RECORDING)
            dictation_bar.set_state("recording")
            dictation_bar.show_bar()

    trevo.state_changed.connect(_on_state_changed)

    # Live transcript preview in the bar
    trevo.raw_transcript_ready.connect(dictation_bar.update_transcript)

    # Audio level meter
    trevo.audio_level_changed.connect(dictation_bar.update_audio_level)

    # Error notifications via tray
    def _on_error(msg: str) -> None:
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
        dlg = SettingsDialog(parent=None)
        if dlg.exec():
            new_settings = dlg.get_settings()
            logger.info("Settings saved: {}", {k: "***" if "key" in k else v for k, v in new_settings.items()})

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

    if hasattr(tray, "knowledge_requested"):
        tray.knowledge_requested.connect(_open_knowledge)

    # Trevo Mode toggle
    def _toggle_trevo_mode():
        if trevo_mode.isVisible():
            trevo_mode.hide_sphere()
        else:
            trevo_mode.show_sphere()

    if hasattr(tray, 'trevo_mode_requested'):
        tray.trevo_mode_requested.connect(_toggle_trevo_mode)

    # Workflow Editor
    def _open_workflow_editor():
        from ui.workflow_editor import WorkflowEditorDialog
        editor = WorkflowEditorDialog(parent=None)
        editor.exec()

    if hasattr(tray, 'workflow_editor_requested'):
        tray.workflow_editor_requested.connect(_open_workflow_editor)

    # Clap detection → toggle Trevo Mode
    from core.clap_detector import ClapDetector
    clap_detector = ClapDetector()
    clap_detector.clap_detected.connect(_toggle_trevo_mode)

    # Connect clap detector to audio stream
    if hasattr(trevo, '_audio_capture') and trevo._audio_capture is not None:
        trevo._audio_capture.audio_chunk.connect(clap_detector.process_audio)

    # When app state changes, update Trevo Mode sphere if visible
    from ui.trevo_mode import TrevoState

    def _update_trevo_state(state: AppState):
        if trevo_mode.isVisible():
            state_map = {
                AppState.IDLE: TrevoState.IDLE,
                AppState.RECORDING: TrevoState.LISTENING,
                AppState.PROCESSING: TrevoState.PROCESSING,
                AppState.COMMAND_MODE: TrevoState.LISTENING,
            }
            trevo_mode.set_state(state_map.get(state, TrevoState.IDLE))

    trevo.state_changed.connect(_update_trevo_state)

    # Morning briefing handler
    def _on_conversation_message(msg: str):
        if msg == "morning_briefing":
            # TODO: Full morning briefing workflow (Phase 2.1 completion)
            trevo_mode.show_sphere()
            trevo_mode.set_state(TrevoState.SPEAKING)

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
    tray.set_engine_status(f"Engine: {engine_name}")
    lang = settings.stt.language
    tray.set_language_status(f"Language: {lang}")

    # --- Show tray -----------------------------------------------------------
    tray.show()

    # --- OS signal handling --------------------------------------------------
    signal.signal(signal.SIGINT, lambda *_: _quit())
    signal.signal(signal.SIGTERM, lambda *_: _quit())

    # Timer trick: periodically return control to Python so signals are handled.
    _signal_timer = QTimer()
    _signal_timer.timeout.connect(lambda: None)
    _signal_timer.start(200)

    logger.info("trevo is running. Press {} to record.", settings.general.hotkey)

    # --- Enter Qt event loop -------------------------------------------------
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
