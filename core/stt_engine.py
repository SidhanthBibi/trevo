"""Abstract base class for Speech-to-Text engines in trevo.

Defines the contract that all STT backends must fulfil, along with shared
data classes for transcript events.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import AsyncGenerator, Optional


@dataclass(frozen=True)
class WordInfo:
    """Timing and confidence info for a single recognised word."""

    word: str
    start_ms: int
    end_ms: int
    confidence: float = 1.0


@dataclass
class TranscriptEvent:
    """A (partial or final) transcript returned by an STT engine."""

    text: str
    is_final: bool
    confidence: float = 0.0
    language: str = ""
    words: list[WordInfo] = field(default_factory=list)
    duration_ms: int = 0


class STTEngine(ABC):
    """Abstract base for all speech-to-text streaming engines."""

    @abstractmethod
    async def start_stream(self) -> None:
        """Initialise the streaming connection / session."""
        ...

    @abstractmethod
    async def send_audio(self, chunk: bytes) -> None:
        """Send a chunk of raw int16 audio to the engine."""
        ...

    @abstractmethod
    async def get_transcripts(self) -> AsyncGenerator[TranscriptEvent, None]:
        """Yield TranscriptEvent objects as they become available."""
        ...
        # Ensure the function is recognised as an async generator:
        yield  # pragma: no cover  # type: ignore[misc]

    @abstractmethod
    async def stop_stream(self) -> None:
        """Gracefully shut down the streaming session."""
        ...
