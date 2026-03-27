"""Global hotkey manager for trevo.

Activation methods — Right Ctrl is the sole control surface:
- Double-tap Right Ctrl: toggle dictation on/off
- Triple-tap Right Ctrl: open command palette
- Quadruple-tap Right Ctrl: toggle Trevo Mode
- Single tap: intentionally ignored (prevents accidental triggers)
- Escape: cancel active recording

Uses pynput instead of the keyboard library because keyboard fails silently
in PyInstaller --windowed mode.
"""

from __future__ import annotations

import threading
import time
from typing import Optional

from pynput import keyboard as pynput_kb
from PyQt6.QtCore import QObject, pyqtSignal

from utils.logger import logger


# Tap detection thresholds
_TAP_MAX_DURATION = 0.4   # max seconds a key can be held to count as a tap
_TAP_WINDOW = 0.45        # seconds to wait after last tap before deciding


class HotkeyManager(QObject):
    """Detects Right Ctrl multi-tap for activation.

    Signals
    -------
    dictation_toggled(bool)
        True = start recording, False = stop recording.
    trevo_mode()
        Emitted on quadruple-tap Right Ctrl.
    command_palette()
        Emitted on triple-tap Right Ctrl.
    cancelled()
        Emitted when Escape is pressed during recording.
    """

    dictation_toggled = pyqtSignal(bool)
    trevo_mode = pyqtSignal()
    command_palette = pyqtSignal()
    cancelled = pyqtSignal()

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._dictation_active = False
        self._registered = False
        self._listener: Optional[pynput_kb.Listener] = None

        # Right Ctrl tap tracking
        self._rctrl_down_time: Optional[float] = None
        self._rctrl_other_key_pressed = False

        # Multi-tap tracking
        self._tap_count: int = 0
        self._tap_decision_timer: Optional[threading.Timer] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def dictation_active(self) -> bool:
        return self._dictation_active

    def start(self) -> None:
        """Register hotkeys and start listening."""
        if self._registered:
            logger.warning("HotkeyManager.start() called but already registered")
            return

        self._listener = pynput_kb.Listener(
            on_press=self._on_press,
            on_release=self._on_release,
        )
        self._listener.daemon = True
        self._listener.start()

        self._registered = True
        logger.info(
            "HotkeyManager started (Right Ctrl: 2x=dictation, 3x=palette, 4x=Trevo)"
        )

    def stop(self) -> None:
        """Unregister all hotkeys."""
        if not self._registered:
            return
        if self._listener is not None:
            self._listener.stop()
            self._listener = None
        if self._tap_decision_timer is not None:
            self._tap_decision_timer.cancel()
            self._tap_decision_timer = None
        self._registered = False
        logger.info("HotkeyManager stopped")

    # ------------------------------------------------------------------
    # Key event handlers
    # ------------------------------------------------------------------

    def _on_press(self, key: pynput_kb.Key | pynput_kb.KeyCode | None) -> None:
        """Handle key press events."""
        if key is None:
            return

        # Track Right Ctrl press
        if key == pynput_kb.Key.ctrl_r:
            if self._rctrl_down_time is None:
                self._rctrl_down_time = time.monotonic()
                self._rctrl_other_key_pressed = False
            return

        # Any other key while RCtrl held invalidates the tap
        if self._rctrl_down_time is not None:
            self._rctrl_other_key_pressed = True

        # Detect Escape
        if key == pynput_kb.Key.esc:
            if self._dictation_active:
                self._dictation_active = False
                self.dictation_toggled.emit(False)
            self.cancelled.emit()
            logger.debug("Cancelled via Escape")

    def _on_release(self, key: pynput_kb.Key | pynput_kb.KeyCode | None) -> None:
        """Handle key release events."""
        if key is None:
            return

        # Track Right Ctrl release — check for clean tap
        if key == pynput_kb.Key.ctrl_r:
            if self._rctrl_down_time is not None:
                elapsed = time.monotonic() - self._rctrl_down_time
                was_clean_tap = (
                    elapsed < _TAP_MAX_DURATION
                    and not self._rctrl_other_key_pressed
                )
                self._rctrl_down_time = None

                if was_clean_tap:
                    self._tap_count += 1
                    # Cancel existing decision timer and start a new one
                    if self._tap_decision_timer is not None:
                        self._tap_decision_timer.cancel()
                    self._tap_decision_timer = threading.Timer(
                        _TAP_WINDOW, self._execute_tap_action,
                    )
                    self._tap_decision_timer.daemon = True
                    self._tap_decision_timer.start()

    # ------------------------------------------------------------------
    # Multi-tap action dispatch
    # ------------------------------------------------------------------

    def _execute_tap_action(self) -> None:
        """Called after tap window expires. Dispatches based on tap count."""
        count = self._tap_count
        self._tap_count = 0
        self._tap_decision_timer = None

        if count == 2:
            self._toggle_dictation()
        elif count == 3:
            logger.info("Command Palette triggered (triple-tap Right Ctrl)")
            self.command_palette.emit()
        elif count >= 4:
            logger.info("Trevo Mode triggered (quad-tap Right Ctrl)")
            self.trevo_mode.emit()
        # count == 1: intentionally no action (prevents accidental triggers)
        elif count == 1:
            logger.debug("Single Right Ctrl tap — ignored")

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _toggle_dictation(self) -> None:
        """Toggle dictation on/off."""
        self._dictation_active = not self._dictation_active
        logger.info("Dictation toggled: {}", self._dictation_active)
        self.dictation_toggled.emit(self._dictation_active)
