"""Database schema initialization and management for Waggle."""

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


def init_schema(db_path: str) -> None:
    """Initialize database schema with idempotent table creation.

    Creates all v2 tables (workers, callers, requests, pending_relays) if they
    don't exist. Safe to call multiple times on the same database without data
    loss or errors.

    Args:
        db_path: Path to SQLite database file
    """
    db_file = Path(db_path)
    db_file.parent.mkdir(parents=True, exist_ok=True)

    with connection(db_path) as conn:
        cursor = conn.cursor()
        schema_file = Path(__file__).parent / "schema.sql"
        ddl = schema_file.read_text()
        cursor.executescript(ddl)


@contextmanager
def connection(db_path: str) -> Iterator[sqlite3.Connection]:
    """Context manager for database connections with automatic cleanup.

    Usage:
        with connection(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM workers")
            # Auto-commits on clean exit

    Args:
        db_path: Path to SQLite database file

    Yields:
        sqlite3.Connection object

    Raises:
        sqlite3.Error: If connection fails due to invalid path or permissions

    The connection is automatically committed on clean exit and closed when the
    context exits. On exception, any uncommitted changes are rolled back before
    closing.
    """
    conn = None
    try:
        try:
            conn = sqlite3.connect(db_path)
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.row_factory = sqlite3.Row
        except (sqlite3.Error, ValueError) as e:
            raise sqlite3.Error(f"Failed to connect to database at {db_path}: {e}")
        yield conn
        if conn:
            conn.commit()
    except Exception:
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            conn.close()


def create_request(
    db_path: str,
    request_id: str,
    caller_id: str,
    operation: str,
    params: str | None = None,
) -> None:
    with connection(db_path) as conn:
        conn.execute(
            "INSERT INTO requests (request_id, caller_id, operation, status, result) VALUES (?, ?, ?, 'pending', ?)",
            (request_id, caller_id, operation, params or ""),
        )


def get_request(db_path: str, request_id: str) -> dict | None:
    with connection(db_path) as conn:
        row = conn.execute(
            "SELECT request_id, status, result FROM requests WHERE request_id = ?",
            (request_id,),
        ).fetchone()
    return dict(row) if row else None


def complete_request(db_path: str, request_id: str, result: str) -> None:
    with connection(db_path) as conn:
        conn.execute(
            "UPDATE requests SET status = 'completed', result = ?, completed_at = CURRENT_TIMESTAMP WHERE request_id = ?",
            (result, request_id),
        )


def fail_request(db_path: str, request_id: str, error: str) -> None:
    with connection(db_path) as conn:
        conn.execute(
            "UPDATE requests SET status = 'failed', result = ?, completed_at = CURRENT_TIMESTAMP WHERE request_id = ?",
            (error, request_id),
        )
