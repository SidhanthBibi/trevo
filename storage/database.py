"""SQLite database manager for trevo."""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Generator, Optional

from utils.logger import logger

from models.custom_dictionary import CustomWord
from models.transcript import Transcript
from storage.migrations import run_migrations


def get_db_path() -> Path:
    """Return the path to the trevo SQLite database."""
    app_dir = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "trevo"
    app_dir.mkdir(parents=True, exist_ok=True)
    return app_dir / "trevo.db"


class DatabaseManager:
    """Thread-safe SQLite database manager for trevo."""

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or get_db_path()
        self._lock = threading.Lock()
        self._ensure_tables()

    # ------------------------------------------------------------------
    # Connection helpers
    # ------------------------------------------------------------------

    @contextmanager
    def _connect(self) -> Generator[sqlite3.Connection, None, None]:
        """Yield a thread-safe database connection."""
        with self._lock:
            conn = sqlite3.connect(str(self.db_path), timeout=10)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

    # ------------------------------------------------------------------
    # Schema setup
    # ------------------------------------------------------------------

    def _ensure_tables(self) -> None:
        """Create tables if they don't exist, then run migrations."""
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS metadata (
                    key   TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS transcripts (
                    id               TEXT PRIMARY KEY,
                    raw_text         TEXT NOT NULL DEFAULT '',
                    polished_text    TEXT NOT NULL DEFAULT '',
                    language         TEXT NOT NULL DEFAULT 'en',
                    app_context      TEXT NOT NULL DEFAULT '{}',
                    duration_seconds REAL NOT NULL DEFAULT 0.0,
                    word_count       INTEGER NOT NULL DEFAULT 0,
                    created_at       TEXT NOT NULL,
                    audio_path       TEXT
                );

                CREATE TABLE IF NOT EXISTS custom_dictionary (
                    id            TEXT PRIMARY KEY,
                    word          TEXT NOT NULL,
                    pronunciation TEXT,
                    category      TEXT,
                    created_at    TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS settings (
                    key   TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS snippets (
                    id        TEXT PRIMARY KEY,
                    trigger   TEXT NOT NULL UNIQUE,
                    expansion TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_transcripts_created_at
                    ON transcripts(created_at);
                CREATE INDEX IF NOT EXISTS idx_transcripts_language
                    ON transcripts(language);
                CREATE INDEX IF NOT EXISTS idx_custom_dictionary_word
                    ON custom_dictionary(word);
                CREATE INDEX IF NOT EXISTS idx_snippets_trigger
                    ON snippets(trigger);
                """
            )
        # Run any pending migrations
        run_migrations(self.db_path)
        logger.debug("Database ready at {}", self.db_path)

    # ------------------------------------------------------------------
    # Transcript CRUD
    # ------------------------------------------------------------------

    def insert_transcript(self, t: Transcript) -> None:
        """Insert a new transcript record."""
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO transcripts
                    (id, raw_text, polished_text, language, app_context,
                     duration_seconds, word_count, created_at, audio_path)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    t.id,
                    t.raw_text,
                    t.polished_text,
                    t.language,
                    json.dumps(t.app_context),
                    t.duration_seconds,
                    t.word_count,
                    t.created_at.isoformat(),
                    t.audio_path,
                ),
            )
        logger.debug("Inserted transcript {}", t.id)

    def get_transcript(self, transcript_id: str) -> Optional[Transcript]:
        """Fetch a single transcript by ID."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM transcripts WHERE id = ?", (transcript_id,)
            ).fetchone()
        return Transcript.from_row(row) if row else None

    def get_all_transcripts(self, limit: int = 100, offset: int = 0) -> list[Transcript]:
        """Return transcripts ordered by created_at descending."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM transcripts ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        return [Transcript.from_row(r) for r in rows]

    def search_transcripts(
        self,
        text: Optional[str] = None,
        language: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 100,
    ) -> list[Transcript]:
        """Search transcripts by text content, language, and/or date range."""
        clauses: list[str] = []
        params: list[Any] = []

        if text:
            clauses.append("(raw_text LIKE ? OR polished_text LIKE ?)")
            like = f"%{text}%"
            params.extend([like, like])
        if language:
            clauses.append("language = ?")
            params.append(language)
        if start_date:
            clauses.append("created_at >= ?")
            params.append(start_date.isoformat())
        if end_date:
            clauses.append("created_at <= ?")
            params.append(end_date.isoformat())

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        query = f"SELECT * FROM transcripts {where} ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [Transcript.from_row(r) for r in rows]

    def delete_transcript(self, transcript_id: str) -> bool:
        """Delete a transcript by ID. Returns True if a row was deleted."""
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM transcripts WHERE id = ?", (transcript_id,)
            )
        deleted = cursor.rowcount > 0
        if deleted:
            logger.debug("Deleted transcript {}", transcript_id)
        return deleted

    def cleanup_old_transcripts(self, before: datetime) -> int:
        """Delete transcripts older than *before*. Returns count deleted."""
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM transcripts WHERE created_at < ?",
                (before.isoformat(),),
            )
        logger.info("Cleaned up {} old transcripts", cursor.rowcount)
        return cursor.rowcount

    # ------------------------------------------------------------------
    # Custom Dictionary CRUD
    # ------------------------------------------------------------------

    def insert_word(self, w: CustomWord) -> None:
        """Insert a custom dictionary word."""
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO custom_dictionary (id, word, pronunciation, category, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (w.id, w.word, w.pronunciation, w.category, w.created_at.isoformat()),
            )
        logger.debug("Inserted custom word '{}'", w.word)

    def get_all_words(self) -> list[CustomWord]:
        """Return all custom dictionary entries."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM custom_dictionary ORDER BY word"
            ).fetchall()
        return [CustomWord.from_row(r) for r in rows]

    def delete_word(self, word_id: str) -> bool:
        """Delete a custom word by ID."""
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM custom_dictionary WHERE id = ?", (word_id,)
            )
        return cursor.rowcount > 0

    # ------------------------------------------------------------------
    # Settings CRUD (key-value)
    # ------------------------------------------------------------------

    def get_setting(self, key: str) -> Optional[str]:
        """Retrieve a setting value by key."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT value FROM settings WHERE key = ?", (key,)
            ).fetchone()
        return row[0] if row else None

    def set_setting(self, key: str, value: str) -> None:
        """Upsert a setting key-value pair."""
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )

    # ------------------------------------------------------------------
    # Snippets CRUD
    # ------------------------------------------------------------------

    def insert_snippet(self, snippet_id: str, trigger: str, expansion: str) -> None:
        """Insert a voice-triggered snippet."""
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO snippets (id, trigger, expansion, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (snippet_id, trigger, expansion, datetime.now().isoformat()),
            )
        logger.debug("Inserted snippet '{}' -> '{}'", trigger, expansion)

    def get_all_snippets(self) -> list[tuple[str, str, str, str]]:
        """Return all snippets as (id, trigger, expansion, created_at) tuples."""
        with self._connect() as conn:
            return conn.execute(
                "SELECT id, trigger, expansion, created_at FROM snippets ORDER BY trigger"
            ).fetchall()

    def delete_snippet(self, snippet_id: str) -> bool:
        """Delete a snippet by ID."""
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM snippets WHERE id = ?", (snippet_id,)
            )
        return cursor.rowcount > 0
