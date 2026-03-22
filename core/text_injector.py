"""Text injection for trevo.

Injects transcribed text into the currently focused application, either by
pasting via the clipboard or by simulating keystrokes as a fallback.
"""

from __future__ import annotations

import time
from typing import Optional

import pyautogui
import pyperclip
from PyQt6.QtCore import QObject

from utils.logger import logger

# Small delay (seconds) after paste to let the target app process it
_POST_PASTE_DELAY: float = 0.05

# Delay between simulated keystrokes (seconds) for typewrite fallback
_TYPEWRITE_INTERVAL: float = 0.01


class TextInjector(QObject):
    """Injects text into the focused window."""

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def inject(self, text: str, *, use_clipboard: bool = True) -> None:
        """Inject *text* into the active window.

        Parameters
        ----------
        text:
            The string to inject.
        use_clipboard:
            If True (default), inject via the clipboard + Ctrl+V.  Falls
            back to pyautogui.typewrite if the clipboard method fails.
        """
        if not text:
            return

        if use_clipboard:
            try:
                self._inject_clipboard(text)
                return
            except Exception as exc:
                logger.warning("Clipboard injection failed ({}), falling back to typewrite", exc)

        self._inject_typewrite(text)

    # ------------------------------------------------------------------
    # Clipboard method
    # ------------------------------------------------------------------

    @staticmethod
    def _inject_clipboard(text: str) -> None:
        """Copy text to clipboard, paste, then restore the original clipboard."""
        # 1. Save current clipboard contents
        original: Optional[str] = None
        try:
            original = pyperclip.paste()
        except Exception:
            pass

        try:
            # 2. Copy our text
            pyperclip.copy(text)

            # 3. Simulate Ctrl+V
            pyautogui.hotkey("ctrl", "v")
            time.sleep(_POST_PASTE_DELAY)

        finally:
            # 4. Restore original clipboard (best-effort)
            if original is not None:
                try:
                    # Small extra delay so the paste is consumed first
                    time.sleep(_POST_PASTE_DELAY)
                    pyperclip.copy(original)
                except Exception as exc:
                    logger.debug("Could not restore clipboard: {}", exc)

        logger.debug("Injected {} chars via clipboard", len(text))

    # ------------------------------------------------------------------
    # Typewrite fallback
    # ------------------------------------------------------------------

    @staticmethod
    def _inject_typewrite(text: str) -> None:
        """Type the text character-by-character using pyautogui.

        pyautogui.typewrite only supports ASCII, so we use the write()
        function which handles Unicode on Windows.
        """
        try:
            pyautogui.write(text, interval=_TYPEWRITE_INTERVAL)
        except Exception:
            # Final fallback — send one character at a time via press()
            for char in text:
                try:
                    pyautogui.press(char)
                except Exception:
                    logger.debug("Could not type character: {!r}", char)
                time.sleep(_TYPEWRITE_INTERVAL)

        logger.debug("Injected {} chars via typewrite", len(text))
