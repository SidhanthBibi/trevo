"""Custom dictionary model for trevo."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from utils.logger import logger


@dataclass
class CustomWord:
    """A single custom word entry for the speech-to-text dictionary."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    word: str = ""
    pronunciation: Optional[str] = None
    category: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)

    # ------------------------------------------------------------------
    # Serialisation helpers
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Serialize the word to a plain dictionary."""
        return {
            "id": self.id,
            "word": self.word,
            "pronunciation": self.pronunciation,
            "category": self.category,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CustomWord:
        """Create a CustomWord from a dictionary."""
        created_at = data.get("created_at")
        if isinstance(created_at, str):
            try:
                created_at = datetime.fromisoformat(created_at)
            except (ValueError, TypeError):
                created_at = datetime.now()
        elif not isinstance(created_at, datetime):
            created_at = datetime.now()

        return cls(
            id=data.get("id", str(uuid.uuid4())),
            word=data.get("word", ""),
            pronunciation=data.get("pronunciation"),
            category=data.get("category"),
            created_at=created_at,
        )

    @classmethod
    def from_row(cls, row: tuple[Any, ...]) -> CustomWord:
        """Create a CustomWord from a database row.

        Expected column order: id, word, pronunciation, category, created_at
        """
        created_at_raw = row[4] if len(row) > 4 else None
        if isinstance(created_at_raw, str):
            try:
                created_at = datetime.fromisoformat(created_at_raw)
            except (ValueError, TypeError):
                created_at = datetime.now()
        else:
            created_at = datetime.now()

        return cls(
            id=row[0] if len(row) > 0 else str(uuid.uuid4()),
            word=row[1] if len(row) > 1 else "",
            pronunciation=row[2] if len(row) > 2 else None,
            category=row[3] if len(row) > 3 else None,
            created_at=created_at,
        )


# ---------------------------------------------------------------------------
# Bulk import / export
# ---------------------------------------------------------------------------

def export_words(words: list[CustomWord], path: Path) -> None:
    """Export a list of CustomWord entries to a JSON file."""
    data = [w.to_dict() for w in words]
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    logger.info("Exported {} custom words to {}", len(words), path)


def import_words(path: Path) -> list[CustomWord]:
    """Import CustomWord entries from a JSON file."""
    if not path.exists():
        logger.warning("Import file not found: {}", path)
        return []

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        logger.error("Expected a JSON array in {}", path)
        return []

    words = [CustomWord.from_dict(entry) for entry in data]
    logger.info("Imported {} custom words from {}", len(words), path)
    return words
