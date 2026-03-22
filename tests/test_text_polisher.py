"""Tests for trevo TextPolisher module."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.text_polisher import TextPolisher, _CONTEXT_PROMPTS, _SHARED_INSTRUCTIONS
from utils.platform_utils import AppContext


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(coro):
    """Run an async coroutine synchronously for testing."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------

class TestTextPolisherInit:

    def test_default_provider_is_openai(self):
        tp = TextPolisher(provider="openai", api_key="fake-key")
        assert tp.provider == "openai"
        assert tp.model == "gpt-4o-mini"

    def test_anthropic_provider(self):
        tp = TextPolisher(provider="anthropic", api_key="fake-key")
        assert tp.provider == "anthropic"
        assert "claude" in tp.model

    def test_ollama_provider_no_key_needed(self):
        tp = TextPolisher(provider="ollama")
        assert tp.provider == "ollama"

    def test_custom_model_override(self):
        tp = TextPolisher(provider="openai", api_key="k", model="gpt-4o")
        assert tp.model == "gpt-4o"

    def test_invalid_provider_raises(self):
        with pytest.raises(ValueError, match="Unsupported provider"):
            TextPolisher(provider="invalid")

    def test_custom_short_phrase_threshold(self):
        tp = TextPolisher(provider="ollama", short_phrase_threshold=5)
        assert tp.short_phrase_threshold == 5


# ---------------------------------------------------------------------------
# Prompt building
# ---------------------------------------------------------------------------

class TestPromptBuilding:
    """Test that context-aware prompts are built correctly."""

    def test_context_prompts_exist_for_all_types(self):
        expected_types = {"email", "chat", "code", "document", "ai_prompt", "generic"}
        assert expected_types.issubset(set(_CONTEXT_PROMPTS.keys()))

    def test_shared_instructions_contain_rules(self):
        assert "filler words" in _SHARED_INSTRUCTIONS.lower()
        assert "grammar" in _SHARED_INSTRUCTIONS.lower()
        assert "ONLY the polished text" in _SHARED_INSTRUCTIONS

    def test_email_context_prompt_mentions_professional(self):
        assert "professional" in _CONTEXT_PROMPTS["email"].lower()

    def test_chat_context_prompt_mentions_conversational(self):
        assert "conversational" in _CONTEXT_PROMPTS["chat"].lower()

    def test_code_context_prompt_mentions_technical(self):
        assert "technical" in _CONTEXT_PROMPTS["code"].lower()

    def test_generic_is_fallback(self):
        assert "generic" in _CONTEXT_PROMPTS


# ---------------------------------------------------------------------------
# Short phrase detection (skip LLM for <10 words)
# ---------------------------------------------------------------------------

class TestShortPhraseSkip:
    """Short phrases should be cleaned locally without calling the LLM."""

    @patch("core.text_polisher._call_openai", new_callable=AsyncMock)
    def test_short_phrase_skips_llm(self, mock_openai):
        tp = TextPolisher(provider="openai", api_key="fake")
        result = _run(tp.polish("hello world"))

        mock_openai.assert_not_called()
        assert isinstance(result, str)

    @patch("core.text_polisher._call_openai", new_callable=AsyncMock)
    def test_single_word_skips_llm(self, mock_openai):
        tp = TextPolisher(provider="openai", api_key="fake")
        result = _run(tp.polish("yes"))

        mock_openai.assert_not_called()
        assert result == "yes"

    @patch("core.text_polisher._call_openai", new_callable=AsyncMock)
    def test_filler_words_removed_in_short_phrase(self, mock_openai):
        tp = TextPolisher(provider="openai", api_key="fake")
        result = _run(tp.polish("um hello uh world"))

        mock_openai.assert_not_called()
        assert "um" not in result.lower()
        assert "uh" not in result.lower()

    @patch("core.text_polisher._call_openai", new_callable=AsyncMock)
    def test_empty_text_returns_as_is(self, mock_openai):
        tp = TextPolisher(provider="openai", api_key="fake")
        result = _run(tp.polish(""))

        mock_openai.assert_not_called()
        assert result == ""

    @patch("core.text_polisher._call_openai", new_callable=AsyncMock)
    def test_whitespace_only_returns_as_is(self, mock_openai):
        tp = TextPolisher(provider="openai", api_key="fake")
        result = _run(tp.polish("   "))

        mock_openai.assert_not_called()
        assert result.strip() == ""


# ---------------------------------------------------------------------------
# Context-aware prompt generation for different app types
# ---------------------------------------------------------------------------

class TestContextAwarePolish:
    """Test that the correct context prompt is selected based on AppContext."""

    @patch("core.text_polisher._call_openai", new_callable=AsyncMock)
    def test_email_context_uses_email_prompt(self, mock_openai):
        mock_openai.return_value = "Polished email text here."
        tp = TextPolisher(provider="openai", api_key="fake")
        ctx = AppContext(app_name="outlook", app_type="email", window_title="Inbox")

        long_text = "this is a long enough sentence that it should definitely trigger the LLM call for polishing purposes"
        _run(tp.polish(long_text, context=ctx))

        mock_openai.assert_called_once()
        system_arg = mock_openai.call_args[0][1]
        assert "email" in system_arg.lower()

    @patch("core.text_polisher._call_openai", new_callable=AsyncMock)
    def test_code_context_uses_code_prompt(self, mock_openai):
        mock_openai.return_value = "Polished code comment."
        tp = TextPolisher(provider="openai", api_key="fake")
        ctx = AppContext(app_name="code", app_type="code", window_title="VS Code")

        long_text = "this is a long enough sentence that it should definitely trigger the LLM call for polishing"
        _run(tp.polish(long_text, context=ctx))

        mock_openai.assert_called_once()
        system_arg = mock_openai.call_args[0][1]
        assert "code" in system_arg.lower()

    @patch("core.text_polisher._call_openai", new_callable=AsyncMock)
    def test_no_context_uses_generic_prompt(self, mock_openai):
        mock_openai.return_value = "Polished generic text."
        tp = TextPolisher(provider="openai", api_key="fake")

        long_text = "this is a long enough sentence that it should definitely trigger the LLM call for polishing"
        _run(tp.polish(long_text, context=None))

        mock_openai.assert_called_once()
        system_arg = mock_openai.call_args[0][1]
        # Generic prompt should include the generic preamble
        assert "polishing dictated text" in system_arg.lower()


# ---------------------------------------------------------------------------
# LLM call mocking
# ---------------------------------------------------------------------------

class TestLLMCallMocking:
    """Test that LLM provider calls are dispatched correctly."""

    @patch("core.text_polisher._call_openai", new_callable=AsyncMock)
    def test_openai_provider_calls_openai(self, mock_openai):
        mock_openai.return_value = "clean text"
        tp = TextPolisher(provider="openai", api_key="fake-key")

        long_text = "this is a really long dictated sentence with many words that exceeds the threshold for short phrases"
        result = _run(tp.polish(long_text))

        mock_openai.assert_called_once()
        assert result == "clean text"

    @patch("core.text_polisher._call_anthropic", new_callable=AsyncMock)
    def test_anthropic_provider_calls_anthropic(self, mock_anthropic):
        mock_anthropic.return_value = "clean text"
        tp = TextPolisher(provider="anthropic", api_key="fake-key")

        long_text = "this is a really long dictated sentence with many words that exceeds the threshold for short phrases"
        result = _run(tp.polish(long_text))

        mock_anthropic.assert_called_once()
        assert result == "clean text"

    @patch("core.text_polisher._call_ollama", new_callable=AsyncMock)
    def test_ollama_provider_calls_ollama(self, mock_ollama):
        mock_ollama.return_value = "clean text"
        tp = TextPolisher(provider="ollama")

        long_text = "this is a really long dictated sentence with many words that exceeds the threshold for short phrases"
        result = _run(tp.polish(long_text))

        mock_ollama.assert_called_once()
        assert result == "clean text"

    @patch("core.text_polisher._call_openai", new_callable=AsyncMock)
    def test_llm_failure_falls_back_to_local_cleanup(self, mock_openai):
        mock_openai.side_effect = RuntimeError("API error")
        tp = TextPolisher(provider="openai", api_key="fake-key")

        long_text = "um this is a really long dictated sentence with uh many words that exceeds the threshold for short phrases"
        result = _run(tp.polish(long_text))

        # Should fall back to local cleanup (filler words removed)
        assert "um" not in result.split()
        assert isinstance(result, str)

    def test_require_key_raises_without_key(self):
        tp = TextPolisher(provider="openai", api_key=None)
        with pytest.raises(ValueError, match="API key required"):
            tp._require_key()
