"""Database connection manager.

Follows LINHMKT pattern: SQLite with WAL mode,
transaction context manager, and schema auto-initialization.

For :memory: databases (tests), a single shared connection is cached
so that tables persist across connect() calls.
"""
from __future__ import annotations

from contextlib import contextmanager
import logging
from pathlib import Path
import re
import sqlite3
from typing import Iterator

from app.db.schema import SCHEMA_SQL

logger = logging.getLogger(__name__)

# Schema version stamped into PRAGMA user_version. Bump when SCHEMA_SQL changes;
# the additive reconcile below is the data-safe migration path of record.
SCHEMA_VERSION = 1

# Lines in a CREATE TABLE body starting with these are table-level constraints,
# NOT columns (so they must not be treated as columns to add).
_CONSTRAINT_KEYWORDS = {"UNIQUE", "PRIMARY", "FOREIGN", "CHECK", "CONSTRAINT"}
_CREATE_TABLE_RE = re.compile(
    r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+(\w+)\s*\((.*?)\);",
    re.IGNORECASE | re.DOTALL,
)
_CREATE_TABLE_STMT_RE = re.compile(r"^\s*CREATE\s+TABLE", re.IGNORECASE)


class Database:
    """SQLite database wrapper with transaction support."""

    def __init__(self, sqlite_path: str):
        self.path = sqlite_path
        self._memory_conn: sqlite3.Connection | None = None

    def initialize(self) -> None:
        """Create missing tables, then run a DATA-SAFE additive migration.

        Called once at app startup; idempotent. **NEVER drops tables or columns.**
        (The old "drop all tables on legacy schema" path was removed — one mistaken
        deploy of an older build could wipe production data.) Schema drift is
        reconciled by ADDING any missing columns via ALTER TABLE ADD COLUMN, which
        preserves every existing row.
        """
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        conn = self.connect()

        # Strip decorative comment lines, then split into individual statements.
        clean_sql = "\n".join(
            line for line in SCHEMA_SQL.splitlines() if not line.strip().startswith("--")
        )
        statements = [s.strip() for s in clean_sql.split(";") if s.strip()]
        table_ddl = [s for s in statements if _CREATE_TABLE_STMT_RE.match(s)]
        other_ddl = [s for s in statements if not _CREATE_TABLE_STMT_RE.match(s)]

        # 1. Ensure tables exist (IF NOT EXISTS — existing tables untouched).
        for stmt in table_ddl:
            conn.execute(stmt)

        # 2. Additive reconcile: ADD any column missing from a (legacy) table.
        #    Data-safe — only ADD COLUMN, never DROP. MUST run before indexes,
        #    since an index can reference a column we add here
        #    (e.g. idx_sessions_profile_id → sessions.profile_id).
        _reconcile_columns(conn)

        # 3. Indexes (+ any remaining DDL) — now all referenced columns exist.
        for stmt in other_ddl:
            conn.execute(stmt)

        # 4. Stamp schema version (record for future migrations).
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        conn.commit()
        logger.info(
            "DB initialized (path=%s, schema_version=%s)", self.path, SCHEMA_VERSION
        )

        # Don't close :memory: connections — they'd lose all data (shared conn).
        if self.path != ":memory:":
            conn.close()

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
        conn.execute("BEGIN IMMEDIATE")
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

    @contextmanager
    def read_transaction(self) -> Iterator[sqlite3.Connection]:
        """Read-only path — NO `BEGIN IMMEDIATE`, so no write-lock contention.

        Under WAL, plain SELECTs read a consistent snapshot and never block the
        writer (nor wait for it). Use for hot read-only paths (authorize,
        poll_events, idempotency replay) so they stop competing for the single
        SQLite write lock (P3/H4). Do NOT write inside this context.
        """
        conn = self.connect()
        try:
            yield conn
        finally:
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
        conn = sqlite3.connect(self.path, check_same_thread=False, timeout=30.0)
        conn.row_factory = sqlite3.Row
        if self.path != ":memory:":
            conn.execute("PRAGMA journal_mode = WAL")
            # WAL + NORMAL is corruption-safe and skips an fsync per commit —
            # a meaningful write-throughput win under concurrent load (P2/M2).
            conn.execute("PRAGMA synchronous = NORMAL")
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


# ============================================================
# Data-safe additive schema migration helpers
# Replace the old destructive "DROP all tables on legacy schema" path.
# ============================================================


def _split_top_level(body: str) -> list[str]:
    """Split a CREATE TABLE body on top-level commas (ignore commas inside parens,
    e.g. `UNIQUE(profile_id, field_name)`)."""
    parts: list[str] = []
    depth = 0
    cur: list[str] = []
    for ch in body:
        if ch == "(":
            depth += 1
            cur.append(ch)
        elif ch == ")":
            depth -= 1
            cur.append(ch)
        elif ch == "," and depth == 0:
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    if cur:
        parts.append("".join(cur))
    return parts


def _parse_schema_columns(sql: str) -> dict[str, dict[str, str]]:
    """Parse SCHEMA_SQL → {table: {column_name: full_column_def}}.

    Table-level constraint lines (UNIQUE/PRIMARY/FOREIGN/...) are skipped so the
    reconcile only ever tries to add real columns. Single source of truth =
    SCHEMA_SQL (no hand-maintained migration list to drift out of sync).
    """
    tables: dict[str, dict[str, str]] = {}
    for match in _CREATE_TABLE_RE.finditer(sql):
        table = match.group(1)
        cols: dict[str, str] = {}
        for raw in _split_top_level(match.group(2)):
            line = re.sub(r"--.*", "", raw).strip()
            if not line:
                continue
            token = re.split(r"[\s(]", line, maxsplit=1)[0]
            if token.upper() in _CONSTRAINT_KEYWORDS:
                continue
            cols[token] = line
        tables[table] = cols
    return tables


def _existing_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    """Current column names of `table` (empty set if the table doesn't exist)."""
    try:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    except sqlite3.OperationalError:
        return set()
    return {row["name"] for row in rows}


def _add_column_safe(
    conn: sqlite3.Connection, table: str, name: str, definition: str
) -> None:
    """ALTER TABLE ADD COLUMN — data-safe. Never drops; degrades to nullable.

    SQLite cannot ADD a NOT-NULL-without-default / UNIQUE / PK column to a table
    that already has rows. In that rare case, add the column as plain nullable so
    existing data survives and the app keeps running (logged loudly for backfill).
    """
    try:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {definition}")
        logger.info("Schema migrate: +column %s.%s", table, name)
        return
    except sqlite3.OperationalError as exc:
        parts = definition.split()
        col_type = parts[1] if len(parts) > 1 else "TEXT"
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {col_type}")
            logger.warning(
                "Schema migrate: +column %s.%s as NULLABLE (constraints dropped: %s). "
                "Backfill manually if needed.",
                table, name, exc,
            )
        except sqlite3.OperationalError as exc2:
            logger.error(
                "Schema migrate: FAILED to add %s.%s (%s). NOT dropping data — "
                "manual migration required.",
                table, name, exc2,
            )


def _reconcile_columns(conn: sqlite3.Connection) -> None:
    """Add any column in SCHEMA_SQL missing from the live DB. Data-safe (no drop)."""
    for table, cols in _parse_schema_columns(SCHEMA_SQL).items():
        existing = _existing_columns(conn, table)
        if not existing:
            continue  # table just created by executescript with all current columns
        for name, definition in cols.items():
            if name not in existing:
                _add_column_safe(conn, table, name, definition)
