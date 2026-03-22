"""Transcript data model for trevo."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from utils.logger import logger


@dataclass
class Transcript:
    """Represents a single transcription record."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    raw_text: str = ""
    polished_text: str = ""
    language: str = "en"
    app_context: dict[str, Any] = field(default_factory=dict)
    duration_seconds: float = 0.0
    word_count: int = 0
    created_at: datetime = field(default_factory=datetime.now)
    audio_path: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize the transcript to a dictionary."""
        return {
            "id": self.id,
            "raw_text": self.raw_text,
            "polished_text": self.polished_text,
            "language": self.language,
            "app_context": self.app_context,
            "duration_seconds": self.duration_seconds,
            "word_count": self.word_count,
            "created_at": self.created_at.isoformat(),
            "audio_path": self.audio_path,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Transcript:
        """Create a Transcript from a dictionary."""
        app_context = data.get("app_context", {})
        if isinstance(app_context, str):
            try:
                app_context = json.loads(app_context)
            except (json.JSONDecodeError, TypeError):
                logger.warning("Failed to parse app_context JSON, using empty dict")
                app_context = {}

        created_at = data.get("created_at")
        if isinstance(created_at, str):
            try:
                created_at = datetime.fromisoformat(created_at)
            except (ValueError, TypeError):
                logger.warning("Failed to parse created_at, using current time")
                created_at = datetime.now()
        elif not isinstance(created_at, datetime):
            created_at = datetime.now()

        return cls(
            id=data.get("id", str(uuid.uuid4())),
            raw_text=data.get("raw_text", ""),
            polished_text=data.get("polished_text", ""),
            language=data.get("language", "en"),
            app_context=app_context,
            duration_seconds=float(data.get("duration_seconds", 0.0)),
            word_count=int(data.get("word_count", 0)),
            created_at=created_at,
            audio_path=data.get("audio_path"),
        )

    @classmethod
    def from_row(cls, row: tuple[Any, ...]) -> Transcript:
        """Create a Transcript from a database row.

        Expected column order:
            id, raw_text, polished_text, language, app_context,
            duration_seconds, word_count, created_at, audio_path
        """
        app_context = row[4] if len(row) > 4 else "{}"
        if isinstance(app_context, str):
            try:
                app_context = json.loads(app_context)
            except (json.JSONDecodeError, TypeError):
                app_context = {}

        created_at_raw = row[7] if len(row) > 7 else None
        if isinstance(created_at_raw, str):
            try:
                created_at = datetime.fromisoformat(created_at_raw)
            except (ValueError, TypeError):
                created_at = datetime.now()
        else:
            created_at = datetime.now()

        return cls(
            id=row[0] if len(row) > 0 else str(uuid.uuid4()),
            raw_text=row[1] if len(row) > 1 else "",
            polished_text=row[2] if len(row) > 2 else "",
            language=row[3] if len(row) > 3 else "en",
            app_context=app_context,
            duration_seconds=float(row[5]) if len(row) > 5 else 0.0,
            word_count=int(row[6]) if len(row) > 6 else 0,
            created_at=created_at,
            audio_path=row[8] if len(row) > 8 else None,
        )
