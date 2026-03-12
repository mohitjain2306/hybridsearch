# backend/app/db.py

import sqlite3
import json
import asyncio
from pathlib import Path
from datetime import datetime
from typing import Optional

from app.models import QueryLog, StatsResponse

_ROOT   = Path(__file__).resolve().parent.parent.parent
DB_PATH = _ROOT / "data/search_logs.db"

SCHEMA_VERSION = 3


# ---------------------------------------------------------------------------
# Migrations
# ---------------------------------------------------------------------------

# Each migration is keyed by the version it produces.
# To add a future migration: add a new entry at the next integer key.
# Never edit existing entries — always append.

MIGRATIONS: dict[int, str] = {
    1: """
        CREATE TABLE IF NOT EXISTS query_logs (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id    TEXT    NOT NULL,
            timestamp     TEXT    NOT NULL,
            query         TEXT    NOT NULL,
            alpha         REAL    NOT NULL,
            top_k         INTEGER NOT NULL,
            latency_ms    REAL    NOT NULL,
            result_count  INTEGER NOT NULL,
            filters       TEXT,
            error         TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_timestamp ON query_logs(timestamp);
        CREATE INDEX IF NOT EXISTS idx_query     ON query_logs(query);
    """,
    2: """
        ALTER TABLE query_logs ADD COLUMN error TEXT;
    """,
    3: """
        ALTER TABLE query_logs ADD COLUMN user_id TEXT NOT NULL;
    """,
}


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------

def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")   # safe for concurrent readers
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


# ---------------------------------------------------------------------------
# Schema versioning
# ---------------------------------------------------------------------------

def _get_schema_version(conn: sqlite3.Connection) -> int:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS schema_meta (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)
    row = conn.execute(
        "SELECT value FROM schema_meta WHERE key = 'version'"
    ).fetchone()
    return int(row["value"]) if row else 0


def _set_schema_version(conn: sqlite3.Connection, version: int) -> None:
    conn.execute("""
        INSERT INTO schema_meta (key, value) VALUES ('version', ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
    """, (str(version),))


def _run_migrations(conn: sqlite3.Connection) -> None:
    current = _get_schema_version(conn)

    if current == SCHEMA_VERSION:
        return

    pending = {v: sql for v, sql in MIGRATIONS.items() if v > current}

    if not pending:
        return

    for version in sorted(pending):
        sql = pending[version]

        # Migration 1 creates query_logs fresh — skip ALTER if table
        # already exists with the column (e.g. on a clean install).
        if version in (2, 3):
            columns = [
                row[1] for row in
                conn.execute("PRAGMA table_info(query_logs)").fetchall()
            ]
            col_name = "error" if version == 2 else "user_id"
            if col_name in columns:
                _set_schema_version(conn, version)
                continue

        try:
            conn.executescript(sql)
            _set_schema_version(conn, version)
            conn.commit()
        except sqlite3.OperationalError as e:
            raise RuntimeError(
                f"Migration to version {version} failed: {e}"
            ) from e


def init_db() -> None:
    """Initialize DB and run any pending migrations. Call once at startup."""
    with get_connection() as conn:
        _run_migrations(conn)


# ---------------------------------------------------------------------------
# Writes
# ---------------------------------------------------------------------------

def _write_log(log: QueryLog) -> None:
    sql = """
        INSERT INTO query_logs
            (request_id, timestamp, query, alpha, top_k,
             latency_ms, result_count, filters, error)
        VALUES
            (:request_id, :timestamp, :query, :alpha, :top_k,
             :latency_ms, :result_count, :filters, :error)
    """
    row = {
        "request_id":   log.request_id,
        "timestamp":    log.timestamp.isoformat(),
        "query":        log.query,
        "alpha":        log.alpha,
        "top_k":        log.top_k,
        "latency_ms":   log.latency_ms,
        "result_count": log.result_count,
        "filters":      json.dumps(log.filters) if log.filters else None,
        "error":        log.error,
    }
    with get_connection() as conn:
        conn.execute(sql, row)


async def log_query(log: QueryLog) -> None:
    """Non-blocking write — runs the synchronous DB call in a thread pool."""
    await asyncio.to_thread(_write_log, log)


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------

def _row_to_log(row: sqlite3.Row) -> QueryLog:
    return QueryLog(
        id=          row["id"],
        request_id=  row["request_id"],
        timestamp=   datetime.fromisoformat(row["timestamp"]),
        query=       row["query"],
        alpha=       row["alpha"],
        top_k=       row["top_k"],
        latency_ms=  row["latency_ms"],
        result_count=row["result_count"],
        filters=     json.loads(row["filters"]) if row["filters"] else None,
        error=       row["error"],
    )


def get_stats(recent_limit: int = 20) -> StatsResponse:
    with get_connection() as conn:
        agg = conn.execute("""
            SELECT
                COUNT(*)        AS total_queries,
                AVG(latency_ms) AS avg_latency_ms,
                AVG(alpha)      AS avg_alpha
            FROM query_logs
        """).fetchone()

        rows = conn.execute("""
            SELECT * FROM query_logs
            ORDER BY timestamp DESC
            LIMIT ?
        """, (recent_limit,)).fetchall()

    return StatsResponse(
        total_queries=  agg["total_queries"] or 0,
        avg_latency_ms= round(agg["avg_latency_ms"] or 0.0, 2),
        avg_alpha=      round(agg["avg_alpha"] or 0.0, 3),
        recent_logs=    [_row_to_log(r) for r in rows],
    )


def get_logs_for_eval(query: Optional[str] = None) -> list[QueryLog]:
    """Fetch logs optionally filtered by query text — used by eval harness."""
    with get_connection() as conn:
        if query:
            rows = conn.execute("""
                SELECT * FROM query_logs
                WHERE query = ?
                ORDER BY timestamp DESC
            """, (query,)).fetchall()
        else:
            rows = conn.execute("""
                SELECT * FROM query_logs ORDER BY timestamp DESC
            """).fetchall()

    return [_row_to_log(r) for r in rows]