"""Database schema initialization and management for Waggle.

Provides idempotent schema initialization that can be safely called from multiple places.
"""

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


def init_schema(db_path: str) -> None:
    """Initialize database schema with idempotent table creation.
    
    Creates the state table if it doesn't exist. Safe to call multiple times
    on the same database without data loss or errors.
    
    Args:
        db_path: Path to SQLite database file
        
    The state table schema:
        - key: TEXT PRIMARY KEY - {name}+{session_id}+{created}
        - repo: TEXT NOT NULL - current working directory (from pwd)
        - status: TEXT NOT NULL - agent state (working, waiting, etc)
        - updated_at: TIMESTAMP - last update time
    """
    # Ensure parent directory exists
    db_file = Path(db_path)
    db_file.parent.mkdir(parents=True, exist_ok=True)
    
    # Use connection context manager for consistency
    with connection(db_path) as conn:
        cursor = conn.cursor()
        schema_file = Path(__file__).parent / "schema.sql"
        ddl = schema_file.read_text()
        cursor.execute(ddl)
        # Auto-commits via context manager


@contextmanager
def connection(db_path: str) -> Iterator[sqlite3.Connection]:
    """Context manager for database connections with automatic cleanup.
    
    Usage:
        with connection(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM state")
            # Auto-commits on clean exit
            
    Args:
        db_path: Path to SQLite database file
        
    Yields:
        sqlite3.Connection object
        
    Raises:
        sqlite3.Error: If connection fails due to invalid path or permissions
        
    The connection is automatically committed on clean exit and closed when the context exits.
    On exception, any uncommitted changes are explicitly rolled back before closing.
    """
    conn = None
    try:
        try:
            conn = sqlite3.connect(db_path)
        except (sqlite3.Error, ValueError) as e:
            raise sqlite3.Error(f"Failed to connect to database at {db_path}: {e}")
        yield conn
        # Auto-commit on successful completion
        if conn:
            conn.commit()
    except Exception:
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            conn.close()
