"""Database connection manager.

Follows LINHMKT pattern: SQLite with WAL mode,
transaction context manager, and schema auto-initialization.

For :memory: databases (tests), a single shared connection is cached
so that tables persist across connect() calls.
"""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import sqlite3
from typing import Iterator

from app.db.schema import SCHEMA_SQL


class Database:
    """SQLite database wrapper with transaction support."""

    def __init__(self, sqlite_path: str):
        self.path = sqlite_path
        self._memory_conn: sqlite3.Connection | None = None

    def initialize(self) -> None:
        """Create all tables if they don't exist.

        Called once at app startup. Safe to call multiple times
        (all DDL uses CREATE TABLE IF NOT EXISTS).
        """
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        conn = self.connect()

        # Check for legacy schema and drop old tables to trigger clean recreate
        # (This avoids OperationalError: no such column due to CREATE TABLE IF NOT EXISTS)
        try:
            # Query a new column in sessions that didn't exist in legacy sessions
            conn.execute("SELECT session_token_hash FROM sessions LIMIT 1")
        except sqlite3.OperationalError as e:
            # Only trigger drop if sessions table actually exists (if it doesn't exist, we get 'no such table: sessions' which is fine)
            if "no such column" in str(e).lower():
                import logging
                logger = logging.getLogger(__name__)
                logger.warning("Legacy database schema detected (missing sessions.session_token_hash). Dropping all legacy tables...")
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tables = [row[0] for row in cursor.fetchall() if not row[0].startswith("sqlite_")]
                for table in tables:
                    cursor.execute(f"DROP TABLE IF EXISTS {table}")
                conn.commit()

        conn.executescript(SCHEMA_SQL)
        conn.commit()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Context manager for a database transaction.

        Commits on success, rolls back on exception.
        For file-based DBs, closes connection after use.
        For :memory: DBs, keeps connection alive (shared).

        Usage:
            with db.transaction() as conn:
                conn.execute("INSERT INTO ...")
                # auto-commit on exit
        """
        conn = self.connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            # Don't close :memory: connections — they'd lose all data
            if self.path != ":memory:":
                conn.close()

    def connect(self) -> sqlite3.Connection:
        """Open a new connection with standard pragmas.

        For :memory: databases, returns the same shared connection
        so that tables and data persist across calls.
        """
        if self.path == ":memory:":
            if self._memory_conn is None:
                self._memory_conn = self._new_connection()
            return self._memory_conn
        return self._new_connection()

    def _new_connection(self) -> sqlite3.Connection:
        """Create a fresh SQLite connection with pragmas."""
        # check_same_thread=False for :memory: DBs (shared conn across threads)
        conn = sqlite3.connect(self.path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        if self.path != ":memory:":
            conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def health_check(self) -> bool:
        """Return True if database is accessible."""
        try:
            conn = self.connect()
            row = conn.execute("SELECT 1 AS ok").fetchone()
            return bool(row and row["ok"] == 1)
        except Exception:
            return False
