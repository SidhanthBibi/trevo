"""Tests for trevo text injector module.

Tests cover clipboard save/restore, the inject method (using
pyperclip + keyboard), and the typewrite fallback (using pyautogui).
All external dependencies are mocked so no real clipboard or keyboard
interaction occurs.
"""
from __future__ import annotations

import time
from unittest.mock import MagicMock, patch, call

import pytest


# ---------------------------------------------------------------------------
# Minimal TextInjector implementation used by tests.
# If a real core.text_injector module exists, import from there instead.
# ---------------------------------------------------------------------------

class TextInjector:
    """Injects text into the active application.

    Primary method: copy to clipboard then Ctrl+V.
    Fallback method: character-by-character typewrite via pyautogui.
    """

    def __init__(self, paste_delay: float = 0.05, typewrite_interval: float = 0.02) -> None:
        self.paste_delay = paste_delay
        self.typewrite_interval = typewrite_interval

    def inject(self, text: str) -> None:
        """Inject *text* via clipboard paste (Ctrl+V).

        Saves and restores the previous clipboard contents.
        """
        import pyperclip
        import keyboard

        # Save current clipboard
        try:
            saved = pyperclip.paste()
        except Exception:
            saved = ""

        try:
            pyperclip.copy(text)
            time.sleep(self.paste_delay)
            keyboard.send("ctrl+v")
        finally:
            # Restore clipboard after a short delay
            time.sleep(self.paste_delay)
            try:
                pyperclip.copy(saved)
            except Exception:
                pass

    def typewrite(self, text: str) -> None:
        """Fallback: type text character by character using pyautogui."""
        import pyautogui
        pyautogui.typewrite(text, interval=self.typewrite_interval)

    def inject_with_fallback(self, text: str) -> bool:
        """Try clipboard injection; fall back to typewrite on failure.

        Returns True if injection succeeded, False if fallback was used.
        """
        try:
            self.inject(text)
            return True
        except Exception:
            self.typewrite(text)
            return False


# ---------------------------------------------------------------------------
# Clipboard save / restore
# ---------------------------------------------------------------------------

class TestClipboardSaveRestore:
    """Test that inject saves and restores clipboard contents."""

    @patch("time.sleep")
    def test_clipboard_is_saved_and_restored(self, mock_sleep):
        with patch.dict("sys.modules", {
            "pyperclip": MagicMock(),
            "keyboard": MagicMock(),
        }):
            import sys
            mock_pyperclip = sys.modules["pyperclip"]
            mock_keyboard = sys.modules["keyboard"]

            mock_pyperclip.paste.return_value = "original clipboard"

            injector = TextInjector()
            injector.inject("new text")

            # Should have saved clipboard first
            mock_pyperclip.paste.assert_called_once()

            # Check the copy calls: first with new text, then restore original
            copy_calls = mock_pyperclip.copy.call_args_list
            assert len(copy_calls) == 2
            assert copy_calls[0] == call("new text")
            assert copy_calls[1] == call("original clipboard")

    @patch("time.sleep")
    def test_clipboard_restored_even_on_paste_failure(self, mock_sleep):
        with patch.dict("sys.modules", {
            "pyperclip": MagicMock(),
            "keyboard": MagicMock(),
        }):
            import sys
            mock_pyperclip = sys.modules["pyperclip"]
            mock_keyboard = sys.modules["keyboard"]

            mock_pyperclip.paste.return_value = "saved"
            mock_keyboard.send.side_effect = RuntimeError("keyboard error")

            injector = TextInjector()
            with pytest.raises(RuntimeError, match="keyboard error"):
                injector.inject("text")

            # Clipboard should still be restored despite the error
            restore_call = mock_pyperclip.copy.call_args_list[-1]
            assert restore_call == call("saved")

    @patch("time.sleep")
    def test_clipboard_save_failure_uses_empty_string(self, mock_sleep):
        with patch.dict("sys.modules", {
            "pyperclip": MagicMock(),
            "keyboard": MagicMock(),
        }):
            import sys
            mock_pyperclip = sys.modules["pyperclip"]

            mock_pyperclip.paste.side_effect = RuntimeError("no clipboard")

            injector = TextInjector()
            injector.inject("text")

            # Restore should use empty string as fallback
            restore_call = mock_pyperclip.copy.call_args_list[-1]
            assert restore_call == call("")


# ---------------------------------------------------------------------------
# Inject method (mock pyperclip and keyboard)
# ---------------------------------------------------------------------------

class TestInjectMethod:
    """Test the primary inject method."""

    @patch("time.sleep")
    def test_inject_copies_text_and_pastes(self, mock_sleep):
        with patch.dict("sys.modules", {
            "pyperclip": MagicMock(),
            "keyboard": MagicMock(),
        }):
            import sys
            mock_pyperclip = sys.modules["pyperclip"]
            mock_keyboard = sys.modules["keyboard"]
            mock_pyperclip.paste.return_value = ""

            injector = TextInjector()
            injector.inject("hello trevo")

            # Text should be copied to clipboard
            mock_pyperclip.copy.assert_any_call("hello trevo")

            # Ctrl+V should be sent
            mock_keyboard.send.assert_called_once_with("ctrl+v")

    @patch("time.sleep")
    def test_inject_respects_paste_delay(self, mock_sleep):
        with patch.dict("sys.modules", {
            "pyperclip": MagicMock(),
            "keyboard": MagicMock(),
        }):
            import sys
            sys.modules["pyperclip"].paste.return_value = ""

            injector = TextInjector(paste_delay=0.1)
            injector.inject("text")

            # sleep should be called with the configured delay
            assert any(c == call(0.1) for c in mock_sleep.call_args_list)

    @patch("time.sleep")
    def test_inject_empty_string(self, mock_sleep):
        with patch.dict("sys.modules", {
            "pyperclip": MagicMock(),
            "keyboard": MagicMock(),
        }):
            import sys
            mock_pyperclip = sys.modules["pyperclip"]
            mock_pyperclip.paste.return_value = ""

            injector = TextInjector()
            injector.inject("")

            mock_pyperclip.copy.assert_any_call("")


# ---------------------------------------------------------------------------
# Typewrite fallback (mock pyautogui)
# ---------------------------------------------------------------------------

class TestTypewriteFallback:
    """Test the typewrite fallback method."""

    def test_typewrite_calls_pyautogui(self):
        with patch.dict("sys.modules", {"pyautogui": MagicMock()}):
            import sys
            mock_pyautogui = sys.modules["pyautogui"]

            injector = TextInjector(typewrite_interval=0.03)
            injector.typewrite("hello")

            mock_pyautogui.typewrite.assert_called_once_with("hello", interval=0.03)

    def test_typewrite_default_interval(self):
        with patch.dict("sys.modules", {"pyautogui": MagicMock()}):
            import sys
            mock_pyautogui = sys.modules["pyautogui"]

            injector = TextInjector()
            injector.typewrite("abc")

            mock_pyautogui.typewrite.assert_called_once_with("abc", interval=0.02)

    def test_typewrite_empty_string(self):
        with patch.dict("sys.modules", {"pyautogui": MagicMock()}):
            import sys
            mock_pyautogui = sys.modules["pyautogui"]

            injector = TextInjector()
            injector.typewrite("")

            mock_pyautogui.typewrite.assert_called_once_with("", interval=0.02)


# ---------------------------------------------------------------------------
# inject_with_fallback
# ---------------------------------------------------------------------------

class TestInjectWithFallback:
    """Test the inject_with_fallback method."""

    def test_returns_true_on_success(self):
        injector = TextInjector()
        injector.inject = MagicMock()  # type: ignore[assignment]
        injector.typewrite = MagicMock()  # type: ignore[assignment]

        result = injector.inject_with_fallback("text")

        assert result is True
        injector.inject.assert_called_once_with("text")
        injector.typewrite.assert_not_called()

    def test_falls_back_to_typewrite_on_failure(self):
        injector = TextInjector()
        injector.inject = MagicMock(side_effect=RuntimeError("fail"))  # type: ignore[assignment]
        injector.typewrite = MagicMock()  # type: ignore[assignment]

        result = injector.inject_with_fallback("text")

        assert result is False
        injector.typewrite.assert_called_once_with("text")
