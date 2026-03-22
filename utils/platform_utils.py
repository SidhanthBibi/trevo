"""Windows-specific utilities for active window/process detection."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

try:
    import win32gui
    import win32process
    import psutil
    _WIN32_AVAILABLE = True
except ImportError:
    _WIN32_AVAILABLE = False


@dataclass
class AppContext:
    app_name: str = "unknown"
    window_title: str = ""
    app_type: str = "generic"
    exe_name: str = ""


_EMAIL_APPS = {"outlook", "thunderbird", "mailbird"}
_BROWSER_EMAIL_KEYWORDS = {"gmail", "outlook.com", "yahoo mail", "protonmail"}
_CHAT_APPS = {"slack", "discord", "teams", "whatsapp", "telegram", "signal"}
_CODE_APPS = {"code", "cursor", "pycharm", "intellij", "webstorm", "vim", "nvim", "sublime_text", "notepad++"}
_DOC_APPS = {"winword", "libreoffice", "wordpad", "notion"}
_AI_APPS = {"claude.ai", "chatgpt", "chat.openai", "bard"}


def get_active_context() -> AppContext:
    if not _WIN32_AVAILABLE:
        return AppContext()
    try:
        hwnd = win32gui.GetForegroundWindow()
        title = win32gui.GetWindowText(hwnd)
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        proc = psutil.Process(pid)
        exe = proc.name().lower().replace(".exe", "")
        return AppContext(
            app_name=exe,
            window_title=title,
            app_type=_classify(exe, title),
            exe_name=exe,
        )
    except Exception:
        return AppContext()


def _classify(exe: str, title: str) -> str:
    combined = (exe + " " + title).lower()
    if any(k in combined for k in _EMAIL_APPS) or any(k in combined for k in _BROWSER_EMAIL_KEYWORDS):
        return "email"
    if any(k in combined for k in _CHAT_APPS):
        return "chat"
    if any(k in combined for k in _CODE_APPS):
        return "code"
    if any(k in combined for k in _DOC_APPS):
        return "document"
    if any(k in combined for k in _AI_APPS):
        return "ai_prompt"
    if "chrome" in combined or "firefox" in combined or "edge" in combined or "opera" in combined:
        return "browser"
    return "generic"
