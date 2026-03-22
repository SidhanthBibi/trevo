"""Simple version-based database schema migrations for trevo."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Callable

from utils.logger import logger

# Current schema version — bump this when adding a new migration.
CURRENT_VERSION = 1

# Registry: version -> migration function.
# Each function receives a sqlite3.Connection that is inside a transaction.
_migrations: dict[int, Callable[[sqlite3.Connection], None]] = {}


def _register(version: int) -> Callable:
    """Decorator to register a migration function for a given schema version."""
    def decorator(fn: Callable[[sqlite3.Connection], None]) -> Callable[[sqlite3.Connection], None]:
        _migrations[version] = fn
        return fn
    return decorator


# ---------------------------------------------------------------------------
# Migration functions
# ---------------------------------------------------------------------------

@_register(1)
def _migrate_v1(conn: sqlite3.Connection) -> None:
    """Initial schema — tables are already created by DatabaseManager.

    This migration only records that version 1 is the baseline. Future
    migrations (v2, v3, ...) will contain ALTER TABLE / CREATE TABLE
    statements as the schema evolves.
    """
    logger.info("Migration v1: baseline schema recorded")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_schema_version(conn: sqlite3.Connection) -> int:
    """Read the current schema version from the metadata table."""
    try:
        row = conn.execute(
            "SELECT value FROM metadata WHERE key = 'schema_version'"
        ).fetchone()
        return int(row[0]) if row else 0
    except sqlite3.OperationalError:
        # metadata table doesn't exist yet
        return 0


def set_schema_version(conn: sqlite3.Connection, version: int) -> None:
    """Write the schema version into the metadata table."""
    conn.execute(
        "INSERT INTO metadata (key, value) VALUES ('schema_version', ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (str(version),),
    )


def run_migrations(db_path: Path) -> None:
    """Apply all pending migrations to the database at *db_path*.

    This function is safe to call multiple times — it will only run
    migrations whose version is above the currently recorded schema version.
    """
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        current = get_schema_version(conn)
        if current >= CURRENT_VERSION:
            logger.debug("Schema is up-to-date (v{})", current)
            return

        for version in range(current + 1, CURRENT_VERSION + 1):
            migration_fn = _migrations.get(version)
            if migration_fn is None:
                logger.error("Missing migration function for v{}", version)
                raise RuntimeError(f"No migration registered for schema version {version}")

            logger.info("Applying migration v{} ...", version)
            migration_fn(conn)
            set_schema_version(conn, version)
            conn.commit()

        logger.info("Migrations complete — schema is now v{}", CURRENT_VERSION)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
