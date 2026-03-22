"""Voice command parsing for trevo dictation and editing commands."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from utils.logger import logger


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

class CommandType(str, Enum):
    EDIT = "edit"
    DICTATION = "dictation"
    NONE = "none"


@dataclass
class CommandResult:
    """Result of parsing a voice utterance for commands."""
    command_type: CommandType = CommandType.NONE
    action: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)
    remaining_text: str = ""


# ---------------------------------------------------------------------------
# Dictation command map (spoken → inserted text)
# ---------------------------------------------------------------------------

_DICTATION_COMMANDS: dict[str, str] = {
    "new line": "\n",
    "newline": "\n",
    "new paragraph": "\n\n",
    "period": ".",
    "full stop": ".",
    "comma": ",",
    "question mark": "?",
    "exclamation mark": "!",
    "exclamation point": "!",
    "colon": ":",
    "semicolon": ";",
    "open parenthesis": "(",
    "close parenthesis": ")",
    "open bracket": "[",
    "close bracket": "]",
    "open quote": '"',
    "close quote": '"',
    "single quote": "'",
    "dash": " - ",
    "hyphen": "-",
    "ellipsis": "...",
    "ampersand": "&",
    "at sign": "@",
    "hashtag": "#",
    "dollar sign": "$",
    "percent sign": "%",
    "asterisk": "*",
    "underscore": "_",
    "slash": "/",
    "backslash": "\\",
    "tab": "\t",
}

# Build a regex that matches any dictation command (longest first to avoid
# partial matches such as "new line" vs "new").
_DICTATION_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(k) for k in sorted(_DICTATION_COMMANDS, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Edit command patterns (regex → action name + parameter extraction)
# ---------------------------------------------------------------------------

_EDIT_PATTERNS: list[tuple[re.Pattern[str], str, list[str]]] = [
    # Tone / style
    (re.compile(r"make\s+(?:this|it)\s+more\s+formal", re.I), "make_formal", []),
    (re.compile(r"make\s+(?:this|it)\s+(?:more\s+)?casual", re.I), "make_casual", []),
    (re.compile(r"make\s+(?:this|it)\s+shorter", re.I), "make_shorter", []),
    (re.compile(r"make\s+(?:this|it)\s+longer", re.I), "make_longer", []),

    # Grammar
    (re.compile(r"fix\s+(?:the\s+)?grammar", re.I), "fix_grammar", []),

    # Translate
    (re.compile(r"translate\s+(?:this\s+)?(?:to|into)\s+(?P<language>\w[\w\s]*)", re.I), "translate", ["language"]),

    # Formatting
    (re.compile(r"add\s+bullet\s+points?", re.I), "add_bullet_points", []),
    (re.compile(r"number\s+these", re.I), "number_list", []),
    (re.compile(r"make\s+(?:this|it)\s+an?\s+email", re.I), "make_email", []),

    # Summarize
    (re.compile(r"summarize\s+(?:this|it)", re.I), "summarize", []),

    # Undo
    (re.compile(r"\bundo\b", re.I), "undo", []),
]


# ---------------------------------------------------------------------------
# CommandParser
# ---------------------------------------------------------------------------

class CommandParser:
    """Parses raw transcription text for editing or dictation commands.

    The parser first tries deterministic regex matching. If no pattern
    matches, it can optionally fall back to an LLM for fuzzy interpretation
    (not yet implemented — reserved for a future provider hook).

    An internal text history stack supports the ``undo`` command.
    """

    def __init__(self, max_history: int = 50) -> None:
        self._history: list[str] = []
        self._max_history = max_history

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def parse(self, text: str) -> CommandResult:
        """Parse *text* and return a :class:`CommandResult`.

        Order of evaluation:
        1. Edit commands (regex patterns).
        2. Dictation commands (punctuation / formatting tokens).
        3. ``CommandType.NONE`` — plain text, no command detected.
        """
        if not text or not text.strip():
            return CommandResult()

        cleaned = text.strip()

        # 1. Check for edit commands
        result = self._match_edit_command(cleaned)
        if result is not None:
            logger.debug("Edit command detected: action={}, params={}", result.action, result.parameters)
            return result

        # 2. Check for dictation commands
        result = self._match_dictation_commands(cleaned)
        if result is not None:
            logger.debug("Dictation command detected: action=insert_symbol")
            return result

        # 3. No command — pass through as plain text
        return CommandResult(command_type=CommandType.NONE, remaining_text=cleaned)

    def push_history(self, text: str) -> None:
        """Push *text* onto the undo history stack."""
        self._history.append(text)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

    def pop_history(self) -> Optional[str]:
        """Pop and return the most recent text from the undo stack, or ``None``."""
        if self._history:
            return self._history.pop()
        return None

    @property
    def history_depth(self) -> int:
        return len(self._history)

    # ------------------------------------------------------------------
    # Edit command matching
    # ------------------------------------------------------------------

    def _match_edit_command(self, text: str) -> Optional[CommandResult]:
        for pattern, action, param_names in _EDIT_PATTERNS:
            m = pattern.search(text)
            if m:
                params: dict[str, Any] = {}
                for name in param_names:
                    try:
                        params[name] = m.group(name).strip()
                    except IndexError:
                        pass

                # Special handling for undo
                if action == "undo":
                    previous = self.pop_history()
                    params["previous_text"] = previous  # may be None

                return CommandResult(
                    command_type=CommandType.EDIT,
                    action=action,
                    parameters=params,
                    remaining_text=text[:m.start()].strip() + " " + text[m.end():].strip(),
                )
        return None

    # ------------------------------------------------------------------
    # Dictation command matching
    # ------------------------------------------------------------------

    def _match_dictation_commands(self, text: str) -> Optional[CommandResult]:
        """Replace dictation keywords with their literal characters.

        If the entire utterance consists solely of dictation commands (and
        whitespace), ``command_type`` is ``DICTATION``. Otherwise the tokens
        are expanded in-place and ``command_type`` is ``NONE`` with the
        expanded text in ``remaining_text``.
        """
        matches = list(_DICTATION_PATTERN.finditer(text))
        if not matches:
            return None

        # Check if the *entire* text is dictation commands
        only_commands = _DICTATION_PATTERN.sub("", text).strip() == ""

        expanded = _DICTATION_PATTERN.sub(lambda m: _DICTATION_COMMANDS[m.group(0).lower()], text)

        if only_commands:
            return CommandResult(
                command_type=CommandType.DICTATION,
                action="insert_symbol",
                parameters={"expanded": expanded.strip()},
            )

        # Mixed: return expanded text as remaining
        return CommandResult(
            command_type=CommandType.DICTATION,
            action="insert_mixed",
            parameters={"expanded": expanded.strip()},
            remaining_text=expanded.strip(),
        )
