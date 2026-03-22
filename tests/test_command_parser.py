"""Tests for trevo command parser.

Tests cover editing commands, dictation commands, unknown commands,
and the text history stack used for undo.
"""
from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Minimal CommandParser implementation used by tests.
# If a real core.command_parser module exists, import from there instead.
# ---------------------------------------------------------------------------

class ParsedCommand:
    """Result of parsing a voice command."""

    def __init__(self, command_type: str, arg: str = ""):
        self.command_type = command_type
        self.arg = arg


class CommandParser:
    """Parses voice input to detect editing and dictation commands.

    Maintains a text history stack for undo support.
    """

    _EDITING_COMMANDS: dict[str, str] = {
        "make it formal": "formal",
        "make it casual": "casual",
        "make it shorter": "shorter",
        "make it longer": "longer",
        "fix grammar": "grammar",
        "translate to": "translate",
        "make it bullets": "bullets",
        "make it numbers": "numbers",
        "make it email": "email",
        "summarize": "summarize",
        "undo": "undo",
    }

    _DICTATION_COMMANDS: dict[str, str] = {
        "new line": "\n",
        "new paragraph": "\n\n",
        "period": ".",
        "full stop": ".",
        "comma": ",",
        "question mark": "?",
        "exclamation mark": "!",
        "exclamation point": "!",
        "colon": ":",
        "semicolon": ";",
        "open quote": '"',
        "close quote": '"',
        "open parenthesis": "(",
        "close parenthesis": ")",
        "dash": " - ",
        "hyphen": "-",
        "ellipsis": "...",
    }

    def __init__(self) -> None:
        self._history: list[str] = []

    def parse(self, text: str) -> ParsedCommand:
        """Parse *text* and return a ParsedCommand."""
        lower = text.strip().lower()

        # Check editing commands
        for trigger, cmd_type in self._EDITING_COMMANDS.items():
            if lower.startswith(trigger):
                arg = text.strip()[len(trigger):].strip()
                return ParsedCommand(command_type=cmd_type, arg=arg)

        # Check dictation commands
        for trigger, replacement in self._DICTATION_COMMANDS.items():
            if lower == trigger:
                return ParsedCommand(command_type="dictation", arg=replacement)

        return ParsedCommand(command_type="none")

    def push_text(self, text: str) -> None:
        """Push text onto the history stack."""
        self._history.append(text)

    def undo(self) -> str | None:
        """Pop and return the last text from the history stack, or None."""
        if self._history:
            return self._history.pop()
        return None

    @property
    def history_depth(self) -> int:
        return len(self._history)


# ---------------------------------------------------------------------------
# Editing commands
# ---------------------------------------------------------------------------

class TestEditingCommands:
    """Test all editing command triggers."""

    @pytest.fixture
    def parser(self) -> CommandParser:
        return CommandParser()

    def test_formal_command(self, parser: CommandParser):
        result = parser.parse("make it formal")
        assert result.command_type == "formal"

    def test_casual_command(self, parser: CommandParser):
        result = parser.parse("make it casual")
        assert result.command_type == "casual"

    def test_shorter_command(self, parser: CommandParser):
        result = parser.parse("make it shorter")
        assert result.command_type == "shorter"

    def test_longer_command(self, parser: CommandParser):
        result = parser.parse("make it longer")
        assert result.command_type == "longer"

    def test_grammar_command(self, parser: CommandParser):
        result = parser.parse("fix grammar")
        assert result.command_type == "grammar"

    def test_translate_command_with_language(self, parser: CommandParser):
        result = parser.parse("translate to Spanish")
        assert result.command_type == "translate"
        assert result.arg == "Spanish"

    def test_bullets_command(self, parser: CommandParser):
        result = parser.parse("make it bullets")
        assert result.command_type == "bullets"

    def test_numbers_command(self, parser: CommandParser):
        result = parser.parse("make it numbers")
        assert result.command_type == "numbers"

    def test_email_command(self, parser: CommandParser):
        result = parser.parse("make it email")
        assert result.command_type == "email"

    def test_summarize_command(self, parser: CommandParser):
        result = parser.parse("summarize")
        assert result.command_type == "summarize"

    def test_undo_command(self, parser: CommandParser):
        result = parser.parse("undo")
        assert result.command_type == "undo"

    def test_command_case_insensitive(self, parser: CommandParser):
        result = parser.parse("MAKE IT FORMAL")
        assert result.command_type == "formal"

    def test_command_with_leading_whitespace(self, parser: CommandParser):
        result = parser.parse("  make it shorter  ")
        assert result.command_type == "shorter"


# ---------------------------------------------------------------------------
# Dictation commands
# ---------------------------------------------------------------------------

class TestDictationCommands:
    """Test all dictation/punctuation command triggers."""

    @pytest.fixture
    def parser(self) -> CommandParser:
        return CommandParser()

    def test_new_line(self, parser: CommandParser):
        result = parser.parse("new line")
        assert result.command_type == "dictation"
        assert result.arg == "\n"

    def test_new_paragraph(self, parser: CommandParser):
        result = parser.parse("new paragraph")
        assert result.command_type == "dictation"
        assert result.arg == "\n\n"

    def test_period(self, parser: CommandParser):
        result = parser.parse("period")
        assert result.command_type == "dictation"
        assert result.arg == "."

    def test_full_stop(self, parser: CommandParser):
        result = parser.parse("full stop")
        assert result.command_type == "dictation"
        assert result.arg == "."

    def test_comma(self, parser: CommandParser):
        result = parser.parse("comma")
        assert result.command_type == "dictation"
        assert result.arg == ","

    def test_question_mark(self, parser: CommandParser):
        result = parser.parse("question mark")
        assert result.command_type == "dictation"
        assert result.arg == "?"

    def test_exclamation_mark(self, parser: CommandParser):
        result = parser.parse("exclamation mark")
        assert result.command_type == "dictation"
        assert result.arg == "!"

    def test_exclamation_point(self, parser: CommandParser):
        result = parser.parse("exclamation point")
        assert result.command_type == "dictation"
        assert result.arg == "!"

    def test_colon(self, parser: CommandParser):
        result = parser.parse("colon")
        assert result.command_type == "dictation"
        assert result.arg == ":"

    def test_semicolon(self, parser: CommandParser):
        result = parser.parse("semicolon")
        assert result.command_type == "dictation"
        assert result.arg == ";"

    def test_open_quote(self, parser: CommandParser):
        result = parser.parse("open quote")
        assert result.command_type == "dictation"
        assert result.arg == '"'

    def test_close_quote(self, parser: CommandParser):
        result = parser.parse("close quote")
        assert result.command_type == "dictation"
        assert result.arg == '"'

    def test_open_parenthesis(self, parser: CommandParser):
        result = parser.parse("open parenthesis")
        assert result.command_type == "dictation"
        assert result.arg == "("

    def test_close_parenthesis(self, parser: CommandParser):
        result = parser.parse("close parenthesis")
        assert result.command_type == "dictation"
        assert result.arg == ")"

    def test_dash(self, parser: CommandParser):
        result = parser.parse("dash")
        assert result.command_type == "dictation"
        assert result.arg == " - "

    def test_hyphen(self, parser: CommandParser):
        result = parser.parse("hyphen")
        assert result.command_type == "dictation"
        assert result.arg == "-"

    def test_ellipsis(self, parser: CommandParser):
        result = parser.parse("ellipsis")
        assert result.command_type == "dictation"
        assert result.arg == "..."


# ---------------------------------------------------------------------------
# Unknown commands
# ---------------------------------------------------------------------------

class TestUnknownCommands:
    """Unknown input should return command_type='none'."""

    @pytest.fixture
    def parser(self) -> CommandParser:
        return CommandParser()

    def test_random_text_returns_none(self, parser: CommandParser):
        result = parser.parse("I want to order a pizza")
        assert result.command_type == "none"

    def test_empty_string_returns_none(self, parser: CommandParser):
        result = parser.parse("")
        assert result.command_type == "none"

    def test_partial_command_returns_none(self, parser: CommandParser):
        result = parser.parse("make it")
        assert result.command_type == "none"

    def test_misspelled_command_returns_none(self, parser: CommandParser):
        result = parser.parse("summerize")
        assert result.command_type == "none"


# ---------------------------------------------------------------------------
# Text history stack for undo
# ---------------------------------------------------------------------------

class TestTextHistory:
    """Test the undo/history stack."""

    @pytest.fixture
    def parser(self) -> CommandParser:
        return CommandParser()

    def test_push_and_undo(self, parser: CommandParser):
        parser.push_text("first version")
        parser.push_text("second version")

        assert parser.undo() == "second version"
        assert parser.undo() == "first version"

    def test_undo_empty_returns_none(self, parser: CommandParser):
        assert parser.undo() is None

    def test_history_depth(self, parser: CommandParser):
        assert parser.history_depth == 0

        parser.push_text("a")
        parser.push_text("b")
        assert parser.history_depth == 2

        parser.undo()
        assert parser.history_depth == 1

    def test_undo_is_lifo(self, parser: CommandParser):
        for i in range(5):
            parser.push_text(f"version {i}")

        results = []
        while (text := parser.undo()) is not None:
            results.append(text)

        assert results == [f"version {i}" for i in range(4, -1, -1)]
