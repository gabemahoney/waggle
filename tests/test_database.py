"""Tests for database module."""

import sqlite3
import tempfile
from pathlib import Path

import pytest

from waggle.database import init_schema, connection


@pytest.fixture
def temp_db():
    """Create a temporary database file."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    yield db_path
    # Cleanup
    Path(db_path).unlink(missing_ok=True)


@pytest.fixture
def temp_db_dir(tmp_path):
    """Create a temporary directory for database."""
    return tmp_path / "test_db"


class TestInitSchema:
    """Tests for init_schema() function."""
    
    def test_creates_state_table_on_first_call(self, temp_db):
        """First call to init_schema() creates the state table."""
        init_schema(temp_db)
        
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        
        # Check table exists
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='state'"
        )
        result = cursor.fetchone()
        assert result is not None
        assert result[0] == 'state'
        
        # Check schema
        cursor.execute("PRAGMA table_info(state)")
        columns = {row[1]: row[2] for row in cursor.fetchall()}
        assert columns == {'key': 'TEXT', 'repo': 'TEXT', 'status': 'TEXT', 'updated_at': 'TIMESTAMP'}
        
        conn.close()
    
    def test_idempotent_repeated_calls_succeed(self, temp_db):
        """Calling init_schema() multiple times doesn't fail."""
        init_schema(temp_db)
        init_schema(temp_db)  # Should not raise
        init_schema(temp_db)  # Should not raise
        
        # Verify table still exists
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='state'"
        )
        assert cursor.fetchone() is not None
        conn.close()
    
    def test_idempotent_preserves_existing_data(self, temp_db):
        """Repeated calls to init_schema() don't delete existing data."""
        init_schema(temp_db)
        
        # Insert test data
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO state (key, repo, status, updated_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)", ("test_key", "/repo/test", "test_status"))
        conn.commit()
        conn.close()
        
        # Call init_schema again
        init_schema(temp_db)
        
        # Verify data still exists
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM state WHERE key = ?", ("test_key",))
        result = cursor.fetchone()
        assert result is not None
        assert result[0] == "test_status"
        conn.close()
    
    def test_creates_parent_directory_if_missing(self, temp_db_dir):
        """init_schema() creates parent directory if it doesn't exist."""
        db_path = temp_db_dir / "subdir" / "test.db"
        assert not db_path.parent.exists()
        
        init_schema(str(db_path))
        
        assert db_path.parent.exists()
        assert db_path.exists()
    
    def test_works_with_new_database_file(self, temp_db_dir):
        """init_schema() works with a database file that doesn't exist yet."""
        db_path = temp_db_dir / "new_db.db"
        temp_db_dir.mkdir(parents=True, exist_ok=True)
        
        assert not db_path.exists()
        init_schema(str(db_path))
        assert db_path.exists()
        
        # Verify table was created
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='state'"
        )
        assert cursor.fetchone() is not None
        conn.close()


class TestConnectionContextManager:
    """Tests for connection() context manager."""
    
    def test_yields_valid_connection(self, temp_db):
        """connection() context manager yields valid Connection."""
        init_schema(temp_db)
        
        with connection(temp_db) as conn:
            assert isinstance(conn, sqlite3.Connection)
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            result = cursor.fetchone()
            assert result == (1,)
    
    def test_closes_connection_after_context_exit(self, temp_db):
        """connection() closes the connection when context exits."""
        init_schema(temp_db)
        
        with connection(temp_db) as conn:
            pass
        
        # Trying to use connection after context should fail
        with pytest.raises(sqlite3.ProgrammingError):
            conn.cursor()
    
    def test_closes_connection_on_exception(self, temp_db):
        """connection() closes connection even when exception occurs."""
        init_schema(temp_db)
        
        try:
            with connection(temp_db) as conn:
                raise ValueError("Test exception")
        except ValueError:
            pass
        
        # Connection should still be closed
        with pytest.raises(sqlite3.ProgrammingError):
            conn.cursor()
    
    def test_rollback_on_exception(self, temp_db):
        """connection() rolls back uncommitted changes on exception."""
        init_schema(temp_db)
        
        # Insert initial data and commit
        with connection(temp_db) as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO state (key, repo, status, updated_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)", ("rollback_test", "/repo/test", "initial"))
            conn.commit()
        
        # Try to update but raise an exception before commit
        try:
            with connection(temp_db) as conn:
                cursor = conn.cursor()
                cursor.execute("UPDATE state SET status = ? WHERE key = ?", ("updated", "rollback_test"))
                # Don't commit - raise exception
                raise ValueError("Simulated error")
        except ValueError:
            pass
        
        # Verify original value is preserved (rollback occurred)
        with connection(temp_db) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT status FROM state WHERE key = ?", ("rollback_test",))
            result = cursor.fetchone()
            assert result[0] == "initial", "Uncommitted change should have been rolled back"
    
    def test_can_perform_database_operations(self, temp_db):
        """connection() can be used for real database operations."""
        init_schema(temp_db)
        
        # Insert data
        with connection(temp_db) as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO state (key, repo, status, updated_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)", ("key1", "/repo/test", "status1"))
            conn.commit()
        
        # Read data
        with connection(temp_db) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT status FROM state WHERE key = ?", ("key1",))
            result = cursor.fetchone()
            assert result[0] == "status1"
    
    def test_error_on_invalid_path(self):
        """connection() raises error for invalid paths."""
        with pytest.raises(sqlite3.Error) as exc_info:
            with connection("/invalid/\x00/path/db.sqlite") as conn:
                pass
        assert "Failed to connect to database" in str(exc_info.value)


class TestUpsertBehavior:
    """Tests for INSERT OR REPLACE (UPSERT) behavior."""
    
    def test_insert_or_replace_creates_new_row(self, temp_db):
        """INSERT OR REPLACE creates a new row when key doesn't exist."""
        init_schema(temp_db)
        
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO state (key, repo, status, updated_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)", ("new_key", "/repo/test", "new_status"))
        conn.commit()
        
        cursor.execute("SELECT status FROM state WHERE key = ?", ("new_key",))
        result = cursor.fetchone()
        assert result is not None
        assert result[0] == "new_status"
        conn.close()
    
    def test_insert_or_replace_updates_existing_row(self, temp_db):
        """INSERT OR REPLACE updates existing row when key exists."""
        init_schema(temp_db)
        
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        
        # Insert initial value
        cursor.execute("INSERT INTO state (key, repo, status, updated_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)", ("test_key", "/repo/test", "old_status"))
        conn.commit()
        
        # Replace with new value
        cursor.execute("INSERT OR REPLACE INTO state (key, repo, status, updated_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)", ("test_key", "/repo/test", "new_status"))
        conn.commit()
        
        # Verify updated
        cursor.execute("SELECT status FROM state WHERE key = ?", ("test_key",))
        result = cursor.fetchone()
        assert result[0] == "new_status"
        
        # Verify only one row exists
        cursor.execute("SELECT COUNT(*) FROM state WHERE key = ?", ("test_key",))
        count = cursor.fetchone()[0]
        assert count == 1
        conn.close()
    
    def test_upsert_multiple_times_maintains_single_row(self, temp_db):
        """Multiple UPSERT operations maintain single row per key."""
        init_schema(temp_db)
        
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        
        # UPSERT same key multiple times
        for i in range(5):
            cursor.execute("INSERT OR REPLACE INTO state (key, repo, status, updated_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)", ("test_key", "/repo/test", f"status_{i}"))
            conn.commit()
        
        # Verify only one row exists with latest value
        cursor.execute("SELECT status FROM state WHERE key = ?", ("test_key",))
        result = cursor.fetchone()
        assert result[0] == "status_4"
        
        cursor.execute("SELECT COUNT(*) FROM state WHERE key = ?", ("test_key",))
        count = cursor.fetchone()[0]
        assert count == 1
        conn.close()


class TestRepoColumn:
    """Tests for repo column behavior in new schema."""
    
    def test_repo_column_stores_working_directory(self, temp_db):
        """Verify repo column stores the working directory path."""
        init_schema(temp_db)
        
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        
        # Insert entry with repo path
        cursor.execute("INSERT INTO state (key, repo, status, updated_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)", 
                      ("session+123", "/home/user/projects/waggle", "working"))
        conn.commit()
        
        # Verify repo column is populated correctly
        cursor.execute("SELECT repo FROM state WHERE key = ?", ("session+123",))
        result = cursor.fetchone()
        assert result[0] == "/home/user/projects/waggle"
        
        conn.close()
    
    def test_different_repos_dont_collide(self, temp_db):
        """Keys with different repos are isolated from each other."""
        init_schema(temp_db)
        
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        
        # Insert keys with different repos
        cursor.execute("INSERT INTO state (key, repo, status, updated_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)", ("session+123", "/repo/path1", "status1"))
        cursor.execute("INSERT INTO state (key, repo, status, updated_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)", ("session+456", "/repo/path2", "status2"))
        conn.commit()
        
        # Verify both keys exist independently
        cursor.execute("SELECT status FROM state WHERE repo = ? AND key = ?", ("/repo/path1", "session+123"))
        result1 = cursor.fetchone()
        assert result1[0] == "status1"
        
        cursor.execute("SELECT status FROM state WHERE repo = ? AND key = ?", ("/repo/path2", "session+456"))
        result2 = cursor.fetchone()
        assert result2[0] == "status2"
        
        conn.close()
    
    def test_same_session_name_different_repos_isolated(self, temp_db):
        """Different session IDs in different repos creates separate entries."""
        init_schema(temp_db)
        
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        
        # Insert different session keys in different repos
        cursor.execute("INSERT INTO state (key, repo, status, updated_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)", ("my_session+001+111", "/home/user/repo1", "migrating database"))
        cursor.execute("INSERT INTO state (key, repo, status, updated_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)", ("my_session+002+222", "/home/user/repo2", "awaiting confirmation"))
        conn.commit()
        
        # Verify both exist with different values
        cursor.execute("SELECT COUNT(*) FROM state")
        count = cursor.fetchone()[0]
        assert count == 2
        
        cursor.execute("SELECT status FROM state WHERE repo = ? AND key = ?", ("/home/user/repo1", "my_session+001+111"))
        assert cursor.fetchone()[0] == "migrating database"
        
        cursor.execute("SELECT status FROM state WHERE repo = ? AND key = ?", ("/home/user/repo2", "my_session+002+222"))
        assert cursor.fetchone()[0] == "awaiting confirmation"
        
        conn.close()
    
    def test_repo_filtering_queries_by_repo_column(self, temp_db):
        """Can filter entries by repo column."""
        init_schema(temp_db)
        
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        
        # Insert multiple keys with different repos
        cursor.execute("INSERT INTO state (key, repo, status, updated_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)", ("session1+001+111", "/repo/a", "status1"))
        cursor.execute("INSERT INTO state (key, repo, status, updated_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)", ("session2+002+222", "/repo/a", "status2"))
        cursor.execute("INSERT INTO state (key, repo, status, updated_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)", ("session3+003+333", "/repo/b", "status3"))
        conn.commit()
        
        # Query keys for specific repo using repo column
        cursor.execute("SELECT key, status FROM state WHERE repo = ?", ("/repo/a",))
        results = cursor.fetchall()
        
        assert len(results) == 2
        assert all(key in ["session1+001+111", "session2+002+222"] for key, _ in results)
        
        conn.close()
    
    def test_multiple_repos_can_safely_use_same_database(self, temp_db):
        """Multiple repos can use the same database without interference."""
        init_schema(temp_db)
        
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        
        # Simulate multiple repos writing to database
        repos = ["/home/user/project1", "/home/user/project2", "/var/www/app"]
        for i, repo in enumerate(repos):
            cursor.execute("INSERT INTO state (key, repo, status, updated_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)", (f"test+{i:03d}", repo, f"status_for_{repo}"))
        conn.commit()
        
        # Verify all repos' data is present and isolated
        cursor.execute("SELECT COUNT(*) FROM state")
        assert cursor.fetchone()[0] == 3
        
        for repo in repos:
            cursor.execute("SELECT status FROM state WHERE repo = ?", (repo,))
            result = cursor.fetchone()
            assert result[0] == f"status_for_{repo}"
        
        conn.close()
