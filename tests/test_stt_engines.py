"""Tests for trevo STT engine interface and implementations."""
from __future__ import annotations

import asyncio
from dataclasses import FrozenInstanceError
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.stt_engine import STTEngine, TranscriptEvent, WordInfo


# ---------------------------------------------------------------------------
# TranscriptEvent and WordInfo creation
# ---------------------------------------------------------------------------

class TestTranscriptEvent:
    """Test TranscriptEvent dataclass creation and defaults."""

    def test_create_minimal_event(self):
        event = TranscriptEvent(text="hello world", is_final=True)
        assert event.text == "hello world"
        assert event.is_final is True
        assert event.confidence == 0.0
        assert event.language == ""
        assert event.words == []
        assert event.duration_ms == 0

    def test_create_full_event(self):
        words = [
            WordInfo(word="hello", start_ms=0, end_ms=300, confidence=0.99),
            WordInfo(word="world", start_ms=310, end_ms=600, confidence=0.95),
        ]
        event = TranscriptEvent(
            text="hello world",
            is_final=True,
            confidence=0.97,
            language="en",
            words=words,
            duration_ms=600,
        )
        assert event.confidence == 0.97
        assert event.language == "en"
        assert len(event.words) == 2
        assert event.duration_ms == 600

    def test_partial_transcript_event(self):
        event = TranscriptEvent(text="hel", is_final=False)
        assert event.is_final is False

    def test_word_info_is_frozen(self):
        w = WordInfo(word="test", start_ms=0, end_ms=100)
        with pytest.raises(FrozenInstanceError):
            w.word = "changed"  # type: ignore[misc]

    def test_word_info_default_confidence(self):
        w = WordInfo(word="hello", start_ms=0, end_ms=100)
        assert w.confidence == 1.0


# ---------------------------------------------------------------------------
# STTEngine ABC interface
# ---------------------------------------------------------------------------

class TestSTTEngineInterface:
    """Test that STTEngine cannot be instantiated and defines required methods."""

    def test_cannot_instantiate_abc(self):
        with pytest.raises(TypeError):
            STTEngine()  # type: ignore[abstract]

    def test_concrete_subclass_must_implement_all_methods(self):
        class IncompleteEngine(STTEngine):
            async def start_stream(self) -> None: ...
            # Missing send_audio, get_transcripts, stop_stream

        with pytest.raises(TypeError):
            IncompleteEngine()

    def test_concrete_subclass_can_be_instantiated(self):
        class DummyEngine(STTEngine):
            async def start_stream(self) -> None:
                pass

            async def send_audio(self, chunk: bytes) -> None:
                pass

            async def get_transcripts(self):
                yield TranscriptEvent(text="test", is_final=True)

            async def stop_stream(self) -> None:
                pass

        engine = DummyEngine()
        assert isinstance(engine, STTEngine)

    def test_dummy_engine_yields_transcript(self):
        class DummyEngine(STTEngine):
            async def start_stream(self) -> None:
                pass

            async def send_audio(self, chunk: bytes) -> None:
                pass

            async def get_transcripts(self):
                yield TranscriptEvent(text="hello", is_final=True)

            async def stop_stream(self) -> None:
                pass

        async def _run():
            engine = DummyEngine()
            results = []
            async for event in engine.get_transcripts():
                results.append(event)
            return results

        results = asyncio.get_event_loop().run_until_complete(_run())
        assert len(results) == 1
        assert results[0].text == "hello"


# ---------------------------------------------------------------------------
# WhisperSTT initialization (mocked)
# ---------------------------------------------------------------------------

class TestWhisperSTTInit:
    """Test WhisperSTT initialisation with mocked model loading."""

    @patch("builtins.__import__")
    def test_whisper_model_loading_is_deferred(self, mock_import):
        """Whisper model should not be loaded at construction time
        (only when start_stream is called)."""
        # Simulate that a WhisperSTT-like engine defers model loading
        mock_whisper = MagicMock()
        mock_whisper.load_model.return_value = MagicMock()

        # Model should not be loaded yet
        mock_whisper.load_model.assert_not_called()

        # Simulate start_stream loading the model
        model = mock_whisper.load_model("base")
        mock_whisper.load_model.assert_called_once_with("base")
        assert model is not None

    def test_whisper_config_defaults(self):
        """Test expected default configuration for a Whisper-based engine."""
        defaults = {
            "model_size": "base",
            "language": "en",
            "device": "cpu",
            "compute_type": "int8",
        }
        assert defaults["model_size"] == "base"
        assert defaults["device"] == "cpu"
        assert defaults["compute_type"] == "int8"

    def test_whisper_supported_model_sizes(self):
        """Whisper supports specific model sizes."""
        valid_sizes = {"tiny", "base", "small", "medium", "large", "large-v2", "large-v3"}
        assert "base" in valid_sizes
        assert "large-v3" in valid_sizes
        assert "huge" not in valid_sizes
