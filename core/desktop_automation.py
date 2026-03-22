"""Safe desktop automation wrappers for trevo Agent Mode.

Provides sandboxed, logged wrappers around common desktop operations:
- Opening applications
- File system operations (create, read, list)
- Clipboard operations
- Window management (focus, minimize, etc.)
- System queries (IP, disk, RAM, battery)

All destructive operations are flagged so the caller can request
user confirmation before execution.
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from utils.logger import logger


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

class RiskLevel(str, Enum):
    """How dangerous an operation is."""
    SAFE = "safe"              # Read-only, no side effects
    LOW = "low"                # Creates files, opens apps
    MEDIUM = "medium"          # Modifies files, changes system state
    HIGH = "high"              # Deletes files, kills processes


@dataclass
class AutomationResult:
    """Result of a desktop automation operation.

    Attributes
    ----------
    success : bool
        Whether the operation completed without error.
    output : str
        Human-readable output or result data.
    risk : RiskLevel
        Risk level of the operation that was performed.
    requires_confirmation : bool
        If True, the operation was NOT executed — caller must confirm first.
    error : str
        Error message if ``success`` is False.
    metadata : dict
        Extra structured data (file paths, PIDs, etc.).
    """
    success: bool = True
    output: str = ""
    risk: RiskLevel = RiskLevel.SAFE
    requires_confirmation: bool = False
    error: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Application launching
# ---------------------------------------------------------------------------

# Common app names → executable or shell command (Windows)
_APP_ALIASES: dict[str, str] = {
    "vs code": "code",
    "vscode": "code",
    "visual studio code": "code",
    "chrome": "chrome",
    "google chrome": "chrome",
    "firefox": "firefox",
    "edge": "msedge",
    "microsoft edge": "msedge",
    "notepad": "notepad",
    "calculator": "calc",
    "explorer": "explorer",
    "file explorer": "explorer",
    "terminal": "wt",
    "windows terminal": "wt",
    "cmd": "cmd",
    "command prompt": "cmd",
    "powershell": "powershell",
    "task manager": "taskmgr",
    "settings": "ms-settings:",
    "paint": "mspaint",
    "word": "winword",
    "excel": "excel",
    "powerpoint": "powerpnt",
    "outlook": "outlook",
    "spotify": "spotify",
    "discord": "discord",
    "slack": "slack",
    "teams": "teams",
    "obs": "obs64",
    "obs studio": "obs64",
    "cursor": "cursor",
    "sublime": "subl",
    "sublime text": "subl",
    "notepad++": "notepad++",
}


def open_application(app_name: str) -> AutomationResult:
    """Open an application by friendly name or executable path.

    Parameters
    ----------
    app_name : str
        Friendly name (e.g. "VS Code", "Chrome") or executable name.

    Returns
    -------
    AutomationResult
        Result with the launched process info.
    """
    normalized = app_name.strip().lower()
    executable = _APP_ALIASES.get(normalized, normalized)

    logger.info("Opening application: '{}' → '{}'", app_name, executable)

    try:
        # Handle ms-settings: and other URI schemes
        if ":" in executable and not executable.startswith(("C:", "D:", "E:")):
            subprocess.Popen(["start", executable], shell=True)
        else:
            subprocess.Popen(
                executable,
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

        return AutomationResult(
            success=True,
            output=f"Opened {app_name}",
            risk=RiskLevel.LOW,
            metadata={"executable": executable},
        )
    except FileNotFoundError:
        logger.warning("Application not found: '{}'", executable)
        return AutomationResult(
            success=False,
            error=f"Application '{app_name}' not found on this system",
            risk=RiskLevel.LOW,
        )
    except Exception as e:
        logger.exception("Failed to open application: '{}'", app_name)
        return AutomationResult(
            success=False,
            error=f"Failed to open {app_name}: {e}",
            risk=RiskLevel.LOW,
        )


# ---------------------------------------------------------------------------
# File system operations
# ---------------------------------------------------------------------------

def create_file(path: str, content: str = "") -> AutomationResult:
    """Create a file at the given path with optional content.

    Parent directories are created automatically.
    Will NOT overwrite existing files — returns a confirmation request instead.
    """
    file_path = Path(path).expanduser().resolve()

    if file_path.exists():
        return AutomationResult(
            success=False,
            output=f"File already exists: {file_path}",
            risk=RiskLevel.MEDIUM,
            requires_confirmation=True,
            error=f"File '{file_path}' already exists. Confirm to overwrite.",
            metadata={"path": str(file_path), "action": "overwrite"},
        )

    logger.info("Creating file: {}", file_path)

    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        return AutomationResult(
            success=True,
            output=f"Created file: {file_path}",
            risk=RiskLevel.LOW,
            metadata={"path": str(file_path), "size": len(content)},
        )
    except Exception as e:
        logger.exception("Failed to create file: {}", file_path)
        return AutomationResult(
            success=False,
            error=f"Failed to create file: {e}",
            risk=RiskLevel.LOW,
        )


def create_file_force(path: str, content: str = "") -> AutomationResult:
    """Create or overwrite a file (used after confirmation)."""
    file_path = Path(path).expanduser().resolve()
    logger.info("Creating/overwriting file: {}", file_path)

    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        return AutomationResult(
            success=True,
            output=f"Created file: {file_path}",
            risk=RiskLevel.MEDIUM,
            metadata={"path": str(file_path), "size": len(content)},
        )
    except Exception as e:
        logger.exception("Failed to create file: {}", file_path)
        return AutomationResult(success=False, error=f"Failed to create file: {e}")


def read_file(path: str, max_lines: int = 200) -> AutomationResult:
    """Read and return the contents of a file.

    Parameters
    ----------
    path : str
        File path to read.
    max_lines : int
        Maximum number of lines to return (safety limit).
    """
    file_path = Path(path).expanduser().resolve()

    if not file_path.exists():
        return AutomationResult(
            success=False,
            error=f"File not found: {file_path}",
            risk=RiskLevel.SAFE,
        )

    if not file_path.is_file():
        return AutomationResult(
            success=False,
            error=f"Not a file: {file_path}",
            risk=RiskLevel.SAFE,
        )

    logger.debug("Reading file: {}", file_path)

    try:
        lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
        truncated = len(lines) > max_lines
        content = "\n".join(lines[:max_lines])
        if truncated:
            content += f"\n... ({len(lines) - max_lines} more lines truncated)"

        return AutomationResult(
            success=True,
            output=content,
            risk=RiskLevel.SAFE,
            metadata={
                "path": str(file_path),
                "total_lines": len(lines),
                "truncated": truncated,
            },
        )
    except Exception as e:
        logger.exception("Failed to read file: {}", file_path)
        return AutomationResult(success=False, error=f"Failed to read file: {e}")


def list_files(
    directory: str,
    pattern: str = "*",
    recursive: bool = False,
    max_results: int = 100,
) -> AutomationResult:
    """List files in a directory, optionally matching a glob pattern.

    Parameters
    ----------
    directory : str
        Directory to search in.
    pattern : str
        Glob pattern (e.g. ``"*.py"``, ``"*.txt"``).
    recursive : bool
        If True, search subdirectories as well.
    max_results : int
        Maximum number of results to return.
    """
    dir_path = Path(directory).expanduser().resolve()

    if not dir_path.exists():
        return AutomationResult(
            success=False,
            error=f"Directory not found: {dir_path}",
            risk=RiskLevel.SAFE,
        )

    logger.debug("Listing files in {} (pattern={})", dir_path, pattern)

    try:
        if recursive:
            matches = list(dir_path.rglob(pattern))
        else:
            matches = list(dir_path.glob(pattern))

        # Sort by name, limit results
        matches.sort(key=lambda p: p.name.lower())
        truncated = len(matches) > max_results
        matches = matches[:max_results]

        listing = "\n".join(str(p) for p in matches)
        if truncated:
            listing += f"\n... (more results truncated)"

        return AutomationResult(
            success=True,
            output=listing,
            risk=RiskLevel.SAFE,
            metadata={
                "directory": str(dir_path),
                "count": len(matches),
                "truncated": truncated,
            },
        )
    except Exception as e:
        logger.exception("Failed to list files in: {}", dir_path)
        return AutomationResult(success=False, error=f"Failed to list files: {e}")


def delete_file(path: str) -> AutomationResult:
    """Request deletion of a file. Always requires confirmation."""
    file_path = Path(path).expanduser().resolve()

    if not file_path.exists():
        return AutomationResult(
            success=False,
            error=f"File not found: {file_path}",
            risk=RiskLevel.HIGH,
        )

    return AutomationResult(
        success=False,
        output=f"Delete {file_path}?",
        risk=RiskLevel.HIGH,
        requires_confirmation=True,
        error="",
        metadata={"path": str(file_path), "action": "delete"},
    )


def delete_file_confirmed(path: str) -> AutomationResult:
    """Actually delete a file (called after user confirmation)."""
    file_path = Path(path).expanduser().resolve()

    logger.info("Deleting file (confirmed): {}", file_path)

    try:
        if file_path.is_dir():
            shutil.rmtree(file_path)
        else:
            file_path.unlink()
        return AutomationResult(
            success=True,
            output=f"Deleted: {file_path}",
            risk=RiskLevel.HIGH,
            metadata={"path": str(file_path)},
        )
    except Exception as e:
        logger.exception("Failed to delete: {}", file_path)
        return AutomationResult(success=False, error=f"Failed to delete: {e}")


# ---------------------------------------------------------------------------
# Clipboard operations
# ---------------------------------------------------------------------------

def get_clipboard() -> AutomationResult:
    """Read the current clipboard text content."""
    try:
        import win32clipboard
        win32clipboard.OpenClipboard()
        try:
            data = win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT)
            return AutomationResult(
                success=True,
                output=data,
                risk=RiskLevel.SAFE,
                metadata={"length": len(data)},
            )
        except TypeError:
            return AutomationResult(
                success=True,
                output="",
                risk=RiskLevel.SAFE,
                metadata={"note": "Clipboard does not contain text"},
            )
        finally:
            win32clipboard.CloseClipboard()
    except ImportError:
        logger.warning("win32clipboard not available")
        return AutomationResult(
            success=False,
            error="win32clipboard not available — install pywin32",
        )
    except Exception as e:
        logger.exception("Failed to read clipboard")
        return AutomationResult(success=False, error=f"Clipboard read failed: {e}")


def set_clipboard(text: str) -> AutomationResult:
    """Set the clipboard text content."""
    try:
        import win32clipboard
        win32clipboard.OpenClipboard()
        try:
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardText(text, win32clipboard.CF_UNICODETEXT)
            return AutomationResult(
                success=True,
                output=f"Copied {len(text)} characters to clipboard",
                risk=RiskLevel.LOW,
                metadata={"length": len(text)},
            )
        finally:
            win32clipboard.CloseClipboard()
    except ImportError:
        logger.warning("win32clipboard not available")
        return AutomationResult(
            success=False,
            error="win32clipboard not available — install pywin32",
        )
    except Exception as e:
        logger.exception("Failed to set clipboard")
        return AutomationResult(success=False, error=f"Clipboard write failed: {e}")


# ---------------------------------------------------------------------------
# Window management
# ---------------------------------------------------------------------------

def focus_window(title_substring: str) -> AutomationResult:
    """Bring a window to the foreground by partial title match.

    Parameters
    ----------
    title_substring : str
        Case-insensitive substring to match against window titles.
    """
    try:
        import win32gui
        import win32con

        target = title_substring.lower()
        found_hwnd: Optional[int] = None

        def _enum_callback(hwnd: int, _: Any) -> bool:
            nonlocal found_hwnd
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd).lower()
                if target in title:
                    found_hwnd = hwnd
                    return False  # Stop enumeration
            return True

        win32gui.EnumWindows(_enum_callback, None)

        if found_hwnd is None:
            return AutomationResult(
                success=False,
                error=f"No visible window matching '{title_substring}'",
                risk=RiskLevel.SAFE,
            )

        win32gui.ShowWindow(found_hwnd, win32con.SW_RESTORE)
        win32gui.SetForegroundWindow(found_hwnd)
        actual_title = win32gui.GetWindowText(found_hwnd)

        return AutomationResult(
            success=True,
            output=f"Focused window: {actual_title}",
            risk=RiskLevel.SAFE,
            metadata={"hwnd": found_hwnd, "title": actual_title},
        )
    except ImportError:
        return AutomationResult(
            success=False,
            error="pywin32 not available for window management",
        )
    except Exception as e:
        logger.exception("Failed to focus window")
        return AutomationResult(success=False, error=f"Window focus failed: {e}")


def minimize_window(title_substring: Optional[str] = None) -> AutomationResult:
    """Minimize a window by title, or the active window if no title given."""
    try:
        import win32gui
        import win32con

        if title_substring:
            # Find the window first
            result = focus_window(title_substring)
            if not result.success:
                return result
            hwnd = result.metadata["hwnd"]
        else:
            hwnd = win32gui.GetForegroundWindow()

        title = win32gui.GetWindowText(hwnd)
        win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)

        return AutomationResult(
            success=True,
            output=f"Minimized: {title}",
            risk=RiskLevel.SAFE,
            metadata={"hwnd": hwnd, "title": title},
        )
    except ImportError:
        return AutomationResult(
            success=False,
            error="pywin32 not available for window management",
        )
    except Exception as e:
        logger.exception("Failed to minimize window")
        return AutomationResult(success=False, error=f"Window minimize failed: {e}")


def list_windows() -> AutomationResult:
    """List all visible windows with their titles."""
    try:
        import win32gui

        windows: list[str] = []

        def _enum_callback(hwnd: int, _: Any) -> bool:
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd)
                if title.strip():
                    windows.append(title)
            return True

        win32gui.EnumWindows(_enum_callback, None)

        return AutomationResult(
            success=True,
            output="\n".join(windows),
            risk=RiskLevel.SAFE,
            metadata={"count": len(windows)},
        )
    except ImportError:
        return AutomationResult(
            success=False,
            error="pywin32 not available for window listing",
        )
    except Exception as e:
        logger.exception("Failed to list windows")
        return AutomationResult(success=False, error=f"Window listing failed: {e}")


# ---------------------------------------------------------------------------
# System queries
# ---------------------------------------------------------------------------

def get_ip_address() -> AutomationResult:
    """Get the local and public IP addresses."""
    info_parts: list[str] = []

    # Local IP
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        info_parts.append(f"Local IP: {local_ip}")
    except Exception:
        info_parts.append("Local IP: unavailable")

    # Public IP (quick HTTP request)
    try:
        import urllib.request
        public_ip = urllib.request.urlopen(
            "https://api.ipify.org", timeout=5
        ).read().decode("utf-8")
        info_parts.append(f"Public IP: {public_ip}")
    except Exception:
        info_parts.append("Public IP: unavailable (no internet or timeout)")

    return AutomationResult(
        success=True,
        output="\n".join(info_parts),
        risk=RiskLevel.SAFE,
    )


def get_disk_space(drive: str = "C:") -> AutomationResult:
    """Get disk space information for a drive."""
    try:
        usage = shutil.disk_usage(drive + "\\")
        total_gb = usage.total / (1024 ** 3)
        used_gb = usage.used / (1024 ** 3)
        free_gb = usage.free / (1024 ** 3)
        pct_used = (usage.used / usage.total) * 100

        output = (
            f"Drive {drive}\n"
            f"  Total: {total_gb:.1f} GB\n"
            f"  Used:  {used_gb:.1f} GB ({pct_used:.1f}%)\n"
            f"  Free:  {free_gb:.1f} GB"
        )
        return AutomationResult(
            success=True,
            output=output,
            risk=RiskLevel.SAFE,
            metadata={
                "drive": drive,
                "total_bytes": usage.total,
                "used_bytes": usage.used,
                "free_bytes": usage.free,
            },
        )
    except Exception as e:
        return AutomationResult(success=False, error=f"Failed to get disk space: {e}")


def get_system_info() -> AutomationResult:
    """Get RAM usage, CPU info, and battery status."""
    parts: list[str] = []

    try:
        import psutil

        # RAM
        mem = psutil.virtual_memory()
        total_gb = mem.total / (1024 ** 3)
        used_gb = mem.used / (1024 ** 3)
        parts.append(
            f"RAM: {used_gb:.1f} / {total_gb:.1f} GB ({mem.percent}% used)"
        )

        # CPU
        cpu_pct = psutil.cpu_percent(interval=0.5)
        cpu_count = psutil.cpu_count()
        parts.append(f"CPU: {cpu_pct}% ({cpu_count} cores)")

        # Battery
        battery = psutil.sensors_battery()
        if battery is not None:
            plugged = "plugged in" if battery.power_plugged else "on battery"
            parts.append(f"Battery: {battery.percent}% ({plugged})")
        else:
            parts.append("Battery: not available (desktop)")

    except ImportError:
        parts.append("psutil not installed — limited system info")
        # Fallback: basic info from os
        parts.append(f"Platform: {sys.platform}")
        parts.append(f"Python: {sys.version}")

    return AutomationResult(
        success=True,
        output="\n".join(parts),
        risk=RiskLevel.SAFE,
    )


def run_system_command(command: str) -> AutomationResult:
    """Run a system command and return its output.

    Only allows a curated set of safe, read-only commands.
    Anything else requires confirmation.
    """
    # Whitelist of safe commands (read-only)
    _SAFE_PREFIXES = (
        "echo", "hostname", "whoami", "date", "time",
        "systeminfo", "ipconfig", "dir", "type", "where",
        "python --version", "node --version", "git --version",
        "git status", "git log", "git branch", "git diff",
    )

    cmd_lower = command.strip().lower()
    is_safe = any(cmd_lower.startswith(prefix) for prefix in _SAFE_PREFIXES)

    if not is_safe:
        return AutomationResult(
            success=False,
            output=f"Command requires confirmation: {command}",
            risk=RiskLevel.HIGH,
            requires_confirmation=True,
            metadata={"command": command, "action": "run_command"},
        )

    logger.info("Running safe command: {}", command)

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        output = result.stdout
        if result.stderr:
            output += f"\n(stderr: {result.stderr})"

        return AutomationResult(
            success=result.returncode == 0,
            output=output.strip(),
            risk=RiskLevel.SAFE,
            metadata={"returncode": result.returncode},
        )
    except subprocess.TimeoutExpired:
        return AutomationResult(
            success=False,
            error=f"Command timed out after 30s: {command}",
            risk=RiskLevel.SAFE,
        )
    except Exception as e:
        logger.exception("Command execution failed: {}", command)
        return AutomationResult(success=False, error=f"Command failed: {e}")


def run_system_command_confirmed(command: str) -> AutomationResult:
    """Run a system command after user confirmation (bypasses whitelist)."""
    logger.info("Running confirmed command: {}", command)

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=60,
        )
        output = result.stdout
        if result.stderr:
            output += f"\n(stderr: {result.stderr})"

        return AutomationResult(
            success=result.returncode == 0,
            output=output.strip(),
            risk=RiskLevel.HIGH,
            metadata={"returncode": result.returncode},
        )
    except subprocess.TimeoutExpired:
        return AutomationResult(
            success=False,
            error=f"Command timed out after 60s: {command}",
        )
    except Exception as e:
        logger.exception("Confirmed command failed: {}", command)
        return AutomationResult(success=False, error=f"Command failed: {e}")
