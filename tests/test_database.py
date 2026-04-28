"""Tests for database module (v2 schema)."""

import sqlite3
from pathlib import Path

import pytest

from waggle.database import init_schema, connection


@pytest.fixture
def temp_db(tmp_path):
    db_path = str(tmp_path / "test.db")
    yield db_path


@pytest.fixture
def initialized_db(temp_db):
    init_schema(temp_db)
    return temp_db


class TestWALMode:
    def test_wal_mode_enabled_after_init_schema(self, initialized_db):
        conn = sqlite3.connect(initialized_db)
        cursor = conn.cursor()
        cursor.execute("PRAGMA journal_mode")
        result = cursor.fetchone()
        conn.close()
        assert result[0] == "wal"


class TestSchemaCreation:
    def test_all_four_tables_created(self, initialized_db):
        conn = sqlite3.connect(initialized_db)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        tables = {row[0] for row in cursor.fetchall()}
        conn.close()
        assert {"workers", "callers", "requests", "pending_relays"} <= tables

    def test_workers_columns(self, initialized_db):
        conn = sqlite3.connect(initialized_db)
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(workers)")
        columns = {row[1] for row in cursor.fetchall()}
        conn.close()
        expected = {
            "worker_id", "caller_id", "session_name", "session_id", "model",
            "repo", "status", "output", "mcp_session_id", "created_at", "updated_at",
        }
        assert columns == expected

    def test_callers_columns(self, initialized_db):
        conn = sqlite3.connect(initialized_db)
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(callers)")
        columns = {row[1] for row in cursor.fetchall()}
        conn.close()
        assert columns == {"caller_id", "caller_type", "cma_session_id", "unreachable", "registered_at"}

    def test_requests_columns(self, initialized_db):
        conn = sqlite3.connect(initialized_db)
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(requests)")
        columns = {row[1] for row in cursor.fetchall()}
        conn.close()
        assert columns == {
            "request_id", "caller_id", "operation", "status",
            "result", "created_at", "completed_at",
        }

    def test_pending_relays_columns(self, initialized_db):
        conn = sqlite3.connect(initialized_db)
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(pending_relays)")
        columns = {row[1] for row in cursor.fetchall()}
        conn.close()
        assert columns == {
            "relay_id", "worker_id", "relay_type", "details",
            "response", "status", "created_at", "resolved_at",
        }


class TestIndexes:
    def test_idx_workers_caller_exists(self, initialized_db):
        conn = sqlite3.connect(initialized_db)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_workers_caller'"
        )
        result = cursor.fetchone()
        conn.close()
        assert result is not None

    def test_idx_requests_caller_exists(self, initialized_db):
        conn = sqlite3.connect(initialized_db)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_requests_caller'"
        )
        result = cursor.fetchone()
        conn.close()
        assert result is not None

    def test_idx_relays_worker_exists(self, initialized_db):
        conn = sqlite3.connect(initialized_db)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_relays_worker'"
        )
        result = cursor.fetchone()
        conn.close()
        assert result is not None


class TestInitSchemaIdempotent:
    def test_three_calls_succeed(self, temp_db):
        init_schema(temp_db)
        init_schema(temp_db)
        init_schema(temp_db)

    def test_idempotent_preserves_data(self, temp_db):
        init_schema(temp_db)

        conn = sqlite3.connect(temp_db)
        conn.execute(
            "INSERT INTO callers (caller_id, caller_type) VALUES (?, ?)",
            ("caller-1", "local"),
        )
        conn.commit()
        conn.close()

        init_schema(temp_db)
        init_schema(temp_db)

        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute("SELECT caller_type FROM callers WHERE caller_id = ?", ("caller-1",))
        result = cursor.fetchone()
        conn.close()
        assert result is not None
        assert result[0] == "local"

    def test_idempotent_tables_still_exist(self, temp_db):
        init_schema(temp_db)
        init_schema(temp_db)
        init_schema(temp_db)

        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cursor.fetchall()}
        conn.close()
        assert {"workers", "callers", "requests", "pending_relays"} <= tables


class TestCRUDRoundTrip:
    def test_workers_insert_and_select(self, initialized_db):
        conn = sqlite3.connect(initialized_db)
        conn.execute(
            "INSERT INTO workers (worker_id, caller_id, session_name, session_id, model, repo)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            ("w-1", "c-1", "my-session", "sess-1", "claude-3", "/repo/path"),
        )
        conn.commit()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT worker_id, caller_id, status FROM workers WHERE worker_id = ?", ("w-1",)
        )
        row = cursor.fetchone()
        conn.close()
        assert row[0] == "w-1"
        assert row[1] == "c-1"
        assert row[2] == "working"  # default

    def test_callers_insert_and_select(self, initialized_db):
        conn = sqlite3.connect(initialized_db)
        conn.execute(
            "INSERT INTO callers (caller_id, caller_type) VALUES (?, ?)", ("c-1", "cma")
        )
        conn.commit()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT caller_id, caller_type FROM callers WHERE caller_id = ?", ("c-1",)
        )
        row = cursor.fetchone()
        conn.close()
        assert row[0] == "c-1"
        assert row[1] == "cma"

    def test_requests_insert_and_select(self, initialized_db):
        conn = sqlite3.connect(initialized_db)
        conn.execute(
            "INSERT INTO requests (request_id, caller_id, operation) VALUES (?, ?, ?)",
            ("req-1", "c-1", "spawn_worker"),
        )
        conn.commit()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT request_id, operation, status FROM requests WHERE request_id = ?", ("req-1",)
        )
        row = cursor.fetchone()
        conn.close()
        assert row[0] == "req-1"
        assert row[1] == "spawn_worker"
        assert row[2] == "pending"  # default

    def test_pending_relays_insert_and_select(self, initialized_db):
        conn = sqlite3.connect(initialized_db)
        conn.execute(
            "INSERT INTO pending_relays (relay_id, worker_id, relay_type, details)"
            " VALUES (?, ?, ?, ?)",
            ("relay-1", "w-1", "permission", '{"message": "allow bash?"}'),
        )
        conn.commit()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT relay_id, relay_type, status FROM pending_relays WHERE relay_id = ?",
            ("relay-1",),
        )
        row = cursor.fetchone()
        conn.close()
        assert row[0] == "relay-1"
        assert row[1] == "permission"
        assert row[2] == "pending"  # default


class TestCheckConstraints:
    def test_invalid_caller_type_raises(self, initialized_db):
        conn = sqlite3.connect(initialized_db)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO callers (caller_id, caller_type) VALUES (?, ?)",
                ("c-bad", "invalid_type"),
            )
            conn.commit()
        conn.close()

    def test_valid_caller_types_accepted(self, initialized_db):
        conn = sqlite3.connect(initialized_db)
        conn.execute(
            "INSERT INTO callers (caller_id, caller_type) VALUES (?, ?)", ("c-cma", "cma")
        )
        conn.execute(
            "INSERT INTO callers (caller_id, caller_type) VALUES (?, ?)", ("c-local", "local")
        )
        conn.commit()
        conn.close()

    def test_invalid_relay_type_raises(self, initialized_db):
        conn = sqlite3.connect(initialized_db)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO pending_relays (relay_id, worker_id, relay_type, details)"
                " VALUES (?, ?, ?, ?)",
                ("r-bad", "w-1", "invalid_type", "{}"),
            )
            conn.commit()
        conn.close()

    def test_valid_relay_types_accepted(self, initialized_db):
        conn = sqlite3.connect(initialized_db)
        conn.execute(
            "INSERT INTO pending_relays (relay_id, worker_id, relay_type, details)"
            " VALUES (?, ?, ?, ?)",
            ("r-perm", "w-1", "permission", "{}"),
        )
        conn.execute(
            "INSERT INTO pending_relays (relay_id, worker_id, relay_type, details)"
            " VALUES (?, ?, ?, ?)",
            ("r-ask", "w-1", "ask", "{}"),
        )
        conn.commit()
        conn.close()


class TestConnectionContextManager:
    def test_commits_on_clean_exit(self, initialized_db):
        with connection(initialized_db) as conn:
            conn.execute(
                "INSERT INTO callers (caller_id, caller_type) VALUES (?, ?)",
                ("c-commit", "local"),
            )

        verify = sqlite3.connect(initialized_db)
        cursor = verify.cursor()
        cursor.execute("SELECT caller_id FROM callers WHERE caller_id = ?", ("c-commit",))
        assert cursor.fetchone() is not None
        verify.close()

    def test_rollback_on_exception(self, initialized_db):
        try:
            with connection(initialized_db) as conn:
                conn.execute(
                    "INSERT INTO callers (caller_id, caller_type) VALUES (?, ?)",
                    ("c-rollback", "local"),
                )
                raise RuntimeError("boom")
        except RuntimeError:
            pass

        verify = sqlite3.connect(initialized_db)
        cursor = verify.cursor()
        cursor.execute("SELECT caller_id FROM callers WHERE caller_id = ?", ("c-rollback",))
        assert cursor.fetchone() is None
        verify.close()

    def test_closes_after_clean_exit(self, initialized_db):
        with connection(initialized_db) as conn:
            pass

        with pytest.raises(sqlite3.ProgrammingError):
            conn.cursor()

    def test_closes_after_exception(self, initialized_db):
        try:
            with connection(initialized_db) as conn:
                raise ValueError("test")
        except ValueError:
            pass

        with pytest.raises(sqlite3.ProgrammingError):
            conn.cursor()


class TestRowFactory:
    def test_row_factory_is_sqlite_row(self, initialized_db):
        with connection(initialized_db) as conn:
            assert conn.row_factory is sqlite3.Row

    def test_dict_like_column_access(self, initialized_db):
        with connection(initialized_db) as conn:
            conn.execute(
                "INSERT INTO callers (caller_id, caller_type) VALUES (?, ?)",
                ("c-row", "cma"),
            )

        with connection(initialized_db) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT caller_id, caller_type FROM callers WHERE caller_id = ?", ("c-row",)
            )
            row = cursor.fetchone()
            assert row["caller_id"] == "c-row"
            assert row["caller_type"] == "cma"


class TestCreatesParentDirectory:
    def test_creates_nested_parent_dirs(self, tmp_path):
        db_path = str(tmp_path / "a" / "b" / "c" / "test.db")
        assert not (tmp_path / "a").exists()
        init_schema(db_path)
        assert Path(db_path).exists()
