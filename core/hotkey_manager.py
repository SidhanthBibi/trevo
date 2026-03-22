"""Global hotkey manager for trevo.

Listens for keyboard shortcuts in a daemon thread and emits PyQt6 signals.
Supports both toggle and push-to-talk modes for dictation.
"""

from __future__ import annotations

import threading
from enum import Enum, auto
from typing import Optional

import keyboard
from PyQt6.QtCore import QObject, pyqtSignal

from utils.logger import logger


class DictationMode(Enum):
    """How the dictation hotkey behaves."""

    TOGGLE = auto()
    PUSH_TO_TALK = auto()


# Default key combos
_HOTKEY_DICTATION = "ctrl+shift+space"
_HOTKEY_COMMAND = "ctrl+shift+c"
_HOTKEY_MUTE = "ctrl+shift+m"
_HOTKEY_CANCEL = "escape"


class HotkeyManager(QObject):
    """Registers global hotkeys and emits signals on activation."""

    dictation_toggled = pyqtSignal(bool)  # True = start, False = stop
    command_mode = pyqtSignal()
    mute_toggled = pyqtSignal()
    cancelled = pyqtSignal()

    def __init__(
        self,
        mode: DictationMode = DictationMode.TOGGLE,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self._mode = mode
        self._dictation_active = False
        self._registered = False
        self._listener_thread: Optional[threading.Thread] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def mode(self) -> DictationMode:
        return self._mode

    @mode.setter
    def mode(self, value: DictationMode) -> None:
        self._mode = value
        logger.info("Dictation mode set to {}", value.name)

    @property
    def dictation_active(self) -> bool:
        return self._dictation_active

    def start(self) -> None:
        """Register hotkeys and start the listener thread."""
        if self._registered:
            logger.warning("HotkeyManager.start() called but already registered")
            return

        self._register_hotkeys()
        self._registered = True

        # keyboard library pumps events in its own thread when we use
        # add_hotkey, but we start an explicit daemon thread for
        # push-to-talk key-up detection via keyboard.hook.
        self._listener_thread = threading.Thread(
            target=self._listener_loop,
            daemon=True,
            name="trevo-hotkey-listener",
        )
        self._listener_thread.start()
        logger.info("HotkeyManager started (mode={})", self._mode.name)

    def stop(self) -> None:
        """Unregister all hotkeys."""
        if not self._registered:
            return
        keyboard.unhook_all()
        self._registered = False
        logger.info("HotkeyManager stopped")

    # ------------------------------------------------------------------
    # Hotkey registration
    # ------------------------------------------------------------------

    def _register_hotkeys(self) -> None:
        if self._mode == DictationMode.TOGGLE:
            keyboard.add_hotkey(
                _HOTKEY_DICTATION,
                self._on_dictation_toggle,
                suppress=True,
            )
        else:
            # Push-to-talk: activate on key-down, deactivate on key-up.
            # Handled via the _listener_loop hook instead.
            pass

        keyboard.add_hotkey(_HOTKEY_COMMAND, self._on_command, suppress=True)
        keyboard.add_hotkey(_HOTKEY_MUTE, self._on_mute, suppress=True)
        keyboard.add_hotkey(_HOTKEY_CANCEL, self._on_cancel, suppress=True)

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def _on_dictation_toggle(self) -> None:
        self._dictation_active = not self._dictation_active
        logger.debug("Dictation toggled: {}", self._dictation_active)
        self.dictation_toggled.emit(self._dictation_active)

    def _on_dictation_push_down(self) -> None:
        if not self._dictation_active:
            self._dictation_active = True
            logger.debug("Push-to-talk: dictation ON")
            self.dictation_toggled.emit(True)

    def _on_dictation_push_up(self) -> None:
        if self._dictation_active:
            self._dictation_active = False
            logger.debug("Push-to-talk: dictation OFF")
            self.dictation_toggled.emit(False)

    def _on_command(self) -> None:
        logger.debug("Command mode activated")
        self.command_mode.emit()

    def _on_mute(self) -> None:
        logger.debug("Mute toggled")
        self.mute_toggled.emit()

    def _on_cancel(self) -> None:
        if self._dictation_active:
            self._dictation_active = False
            self.dictation_toggled.emit(False)
        logger.debug("Cancelled")
        self.cancelled.emit()

    # ------------------------------------------------------------------
    # Push-to-talk listener
    # ------------------------------------------------------------------

    def _listener_loop(self) -> None:
        """Daemon thread that watches for push-to-talk key-up events."""
        if self._mode != DictationMode.PUSH_TO_TALK:
            return

        ptt_keys = keyboard.parse_hotkey(_HOTKEY_DICTATION)
        pressed_keys: set[int] = set()

        def _on_key_event(event: keyboard.KeyboardEvent) -> None:
            scan = event.scan_code
            if event.event_type == keyboard.KEY_DOWN:
                pressed_keys.add(scan)
                # Check if all PTT keys are held
                if all(
                    any(sc in pressed_keys for sc in step)
                    for step in ptt_keys
                ):
                    self._on_dictation_push_down()
            elif event.event_type == keyboard.KEY_UP:
                pressed_keys.discard(scan)
                if self._dictation_active:
                    self._on_dictation_push_up()

        keyboard.hook(_on_key_event)
        # Block to keep the daemon thread alive while registered
        keyboard.wait()  # type: ignore[call-overload]
