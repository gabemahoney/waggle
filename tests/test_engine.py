"""Unit tests for waggle.engine module — core async engine."""

import asyncio
import sqlite3
import uuid
from unittest.mock import AsyncMock, patch

import pytest

from waggle import engine
from waggle.database import init_schema, connection


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    """Temp database with schema initialized; engine config patched to use it."""
    path = str(tmp_path / "test.db")
    init_schema(path)
    repos_path = str(tmp_path / "repos")

    mock_config = {
        "database_path": path,
        "max_workers": 3,
        "repos_path": repos_path,
    }

    monkeypatch.setattr("waggle.config.get_config", lambda: mock_config)
    monkeypatch.setattr("waggle.engine._db_path", lambda: path)
    return path


@pytest.fixture
def registered_caller(db_path):
    """Pre-register a caller for tests that need one."""
    asyncio.run(engine.register_caller("test-caller", "local"))
    return "test-caller"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _insert_worker(
    db_path,
    caller_id="test-caller",
    status="working",
    model="sonnet",
    repo="/local/repo",
):
    """Insert a worker row directly into the DB and return (worker_id, session_id, session_name)."""
    worker_id = str(uuid.uuid4())
    session_name = f"waggle-{worker_id[:8]}"
    session_id = f"${uuid.uuid4().hex[:4]}"
    with connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO workers
                (worker_id, caller_id, session_name, session_id, model, repo, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (worker_id, caller_id, session_name, session_id, model, repo, status),
        )
    return worker_id, session_id, session_name


def _insert_pending_relay(db_path, worker_id, relay_type="permission", details="{}"):
    """Insert a pending relay row and return its relay_id."""
    relay_id = str(uuid.uuid4())
    with connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO pending_relays
                (relay_id, worker_id, relay_type, details, status)
            VALUES (?, ?, ?, ?, 'pending')
            """,
            (relay_id, worker_id, relay_type, details),
        )
    return relay_id


# ---------------------------------------------------------------------------
# register_caller
# ---------------------------------------------------------------------------


class TestRegisterCaller:
    """Tests for engine.register_caller()."""

    @pytest.mark.asyncio
    async def test_new_caller_returns_caller_id(self, db_path):
        """Registering a new caller returns {"caller_id": str}."""
        result = await engine.register_caller("caller-1", "local")
        assert result == {"caller_id": "caller-1"}

    @pytest.mark.asyncio
    async def test_new_caller_persisted_to_db(self, db_path):
        """New caller is written to the callers table."""
        await engine.register_caller("caller-persist", "cma", "cma-sess-001")

        with connection(db_path) as conn:
            row = conn.execute(
                "SELECT caller_id, caller_type, cma_session_id FROM callers WHERE caller_id = ?",
                ("caller-persist",),
            ).fetchone()

        assert row is not None
        assert row["caller_type"] == "cma"
        assert row["cma_session_id"] == "cma-sess-001"

    @pytest.mark.asyncio
    async def test_upsert_existing_caller_updates_type(self, db_path):
        """Re-registering an existing caller updates its type and returns same caller_id."""
        await engine.register_caller("caller-upsert", "local")
        result = await engine.register_caller("caller-upsert", "cma", "new-session")

        assert result == {"caller_id": "caller-upsert"}

        with connection(db_path) as conn:
            row = conn.execute(
                "SELECT caller_type, cma_session_id FROM callers WHERE caller_id = ?",
                ("caller-upsert",),
            ).fetchone()

        assert row["caller_type"] == "cma"
        assert row["cma_session_id"] == "new-session"

    @pytest.mark.asyncio
    async def test_upsert_keeps_single_row(self, db_path):
        """Multiple registrations with the same caller_id produce exactly one row."""
        for i in range(3):
            await engine.register_caller("caller-unique", "local")

        with connection(db_path) as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM callers WHERE caller_id = ?",
                ("caller-unique",),
            ).fetchone()[0]

        assert count == 1


# ---------------------------------------------------------------------------
# spawn_worker
# ---------------------------------------------------------------------------


class TestSpawnWorker:
    """Tests for engine.spawn_worker()."""

    @pytest.mark.asyncio
    async def test_success_returns_worker_id_and_session_name(self, db_path, registered_caller):
        """Successful spawn returns dict with worker_id and session_name."""
        with (
            patch("waggle.engine.tmux.clone_or_update_repo_async", new_callable=AsyncMock) as mock_clone,
            patch("waggle.engine.tmux.create_session", new_callable=AsyncMock) as mock_create,
            patch("waggle.engine.tmux.launch_agent_in_pane", new_callable=AsyncMock) as mock_launch,
        ):
            mock_clone.return_value = "/local/repo"
            mock_create.return_value = {
                "status": "success",
                "session_id": "$1",
                "session_name": "waggle-test",
                "session_created": "1234567890",
                "worker_id": "irrelevant",
            }
            mock_launch.return_value = {"status": "success"}

            result = await engine.spawn_worker(registered_caller, "sonnet", "/local/repo")

        assert "worker_id" in result
        assert "session_name" in result
        assert "error" not in result

    @pytest.mark.asyncio
    async def test_success_creates_db_row_with_working_status(self, db_path, registered_caller):
        """Successful spawn writes a workers row with status='working'."""
        with (
            patch("waggle.engine.tmux.clone_or_update_repo_async", new_callable=AsyncMock) as mock_clone,
            patch("waggle.engine.tmux.create_session", new_callable=AsyncMock) as mock_create,
            patch("waggle.engine.tmux.launch_agent_in_pane", new_callable=AsyncMock) as mock_launch,
        ):
            mock_clone.return_value = "/local/repo"
            mock_create.return_value = {
                "status": "success",
                "session_id": "$42",
                "session_name": "waggle-test",
                "session_created": "1234567890",
                "worker_id": "irrelevant",
            }
            mock_launch.return_value = {"status": "success"}

            result = await engine.spawn_worker(registered_caller, "haiku", "/local/repo")

        worker_id = result["worker_id"]
        with connection(db_path) as conn:
            row = conn.execute(
                "SELECT * FROM workers WHERE worker_id = ?",
                (worker_id,),
            ).fetchone()

        assert row is not None
        assert row["status"] == "working"
        assert row["caller_id"] == registered_caller
        assert row["model"] == "haiku"

    @pytest.mark.asyncio
    async def test_auto_generated_session_name(self, db_path, registered_caller):
        """When session_name is not provided, it is auto-generated as waggle-{worker_id[:8]}."""
        with (
            patch("waggle.engine.tmux.clone_or_update_repo_async", new_callable=AsyncMock) as mock_clone,
            patch("waggle.engine.tmux.create_session", new_callable=AsyncMock) as mock_create,
            patch("waggle.engine.tmux.launch_agent_in_pane", new_callable=AsyncMock) as mock_launch,
        ):
            mock_clone.return_value = "/local/repo"
            mock_create.return_value = {
                "status": "success",
                "session_id": "$5",
                "session_name": "ignored",
                "session_created": "0",
                "worker_id": "ignored",
            }
            mock_launch.return_value = {"status": "success"}

            result = await engine.spawn_worker(registered_caller, "sonnet", "/local/repo")

        worker_id = result["worker_id"]
        expected_prefix = f"waggle-{worker_id[:8]}"
        assert result["session_name"] == expected_prefix

    @pytest.mark.asyncio
    async def test_explicit_session_name_is_used(self, db_path, registered_caller):
        """When session_name is provided explicitly, it is used verbatim."""
        with (
            patch("waggle.engine.tmux.clone_or_update_repo_async", new_callable=AsyncMock) as mock_clone,
            patch("waggle.engine.tmux.create_session", new_callable=AsyncMock) as mock_create,
            patch("waggle.engine.tmux.launch_agent_in_pane", new_callable=AsyncMock) as mock_launch,
        ):
            mock_clone.return_value = "/local/repo"
            mock_create.return_value = {
                "status": "success",
                "session_id": "$7",
                "session_name": "my-custom-session",
                "session_created": "0",
                "worker_id": "ignored",
            }
            mock_launch.return_value = {"status": "success"}

            result = await engine.spawn_worker(
                registered_caller, "sonnet", "/local/repo", session_name="my-custom-session"
            )

        assert result["session_name"] == "my-custom-session"

    @pytest.mark.asyncio
    async def test_concurrency_limit_reached(self, db_path, registered_caller):
        """spawn_worker returns concurrency_limit_reached when max_workers active workers exist."""
        # Insert max_workers (3) active workers
        for _ in range(3):
            _insert_worker(db_path, caller_id=registered_caller, status="working")

        with (
            patch("waggle.engine.tmux.clone_or_update_repo_async", new_callable=AsyncMock) as mock_clone,
            patch("waggle.engine.tmux.create_session", new_callable=AsyncMock) as mock_create,
            patch("waggle.engine.tmux.launch_agent_in_pane", new_callable=AsyncMock) as mock_launch,
        ):
            result = await engine.spawn_worker(registered_caller, "sonnet", "/local/repo")

        assert result == {"error": "concurrency_limit_reached"}
        mock_clone.assert_not_called()
        mock_create.assert_not_called()
        mock_launch.assert_not_called()

    @pytest.mark.asyncio
    async def test_done_workers_not_counted_against_limit(self, db_path, registered_caller):
        """Workers with status='done' do not count toward the concurrency limit."""
        # Insert max_workers done workers — should not block new spawn
        for _ in range(3):
            _insert_worker(db_path, caller_id=registered_caller, status="done")

        with (
            patch("waggle.engine.tmux.clone_or_update_repo_async", new_callable=AsyncMock) as mock_clone,
            patch("waggle.engine.tmux.create_session", new_callable=AsyncMock) as mock_create,
            patch("waggle.engine.tmux.launch_agent_in_pane", new_callable=AsyncMock) as mock_launch,
        ):
            mock_clone.return_value = "/local/repo"
            mock_create.return_value = {
                "status": "success",
                "session_id": "$9",
                "session_name": "w",
                "session_created": "0",
                "worker_id": "x",
            }
            mock_launch.return_value = {"status": "success"}

            result = await engine.spawn_worker(registered_caller, "sonnet", "/local/repo")

        assert "worker_id" in result

    @pytest.mark.asyncio
    async def test_repo_clone_failure_returns_error(self, db_path, registered_caller):
        """Clone failure is caught and returns repo_clone_failed error."""
        with patch("waggle.engine.tmux.clone_or_update_repo_async", new_callable=AsyncMock) as mock_clone:
            mock_clone.side_effect = RuntimeError("git clone failed")

            result = await engine.spawn_worker(registered_caller, "sonnet", "https://github.com/foo/bar")

        assert "error" in result
        assert result["error"].startswith("repo_clone_failed:")

    @pytest.mark.asyncio
    async def test_session_creation_failure_returns_error(self, db_path, registered_caller):
        """create_session failure returns the error message."""
        with (
            patch("waggle.engine.tmux.clone_or_update_repo_async", new_callable=AsyncMock) as mock_clone,
            patch("waggle.engine.tmux.create_session", new_callable=AsyncMock) as mock_create,
        ):
            mock_clone.return_value = "/local/repo"
            mock_create.return_value = {"status": "error", "message": "session already exists"}

            result = await engine.spawn_worker(registered_caller, "sonnet", "/local/repo")

        assert "error" in result
        assert "session already exists" in result["error"]

    @pytest.mark.asyncio
    async def test_agent_launch_failure_kills_session_and_returns_error(self, db_path, registered_caller):
        """launch_agent_in_pane failure triggers kill_session and returns error."""
        with (
            patch("waggle.engine.tmux.clone_or_update_repo_async", new_callable=AsyncMock) as mock_clone,
            patch("waggle.engine.tmux.create_session", new_callable=AsyncMock) as mock_create,
            patch("waggle.engine.tmux.launch_agent_in_pane", new_callable=AsyncMock) as mock_launch,
            patch("waggle.engine.tmux.kill_session", new_callable=AsyncMock) as mock_kill,
        ):
            mock_clone.return_value = "/local/repo"
            mock_create.return_value = {
                "status": "success",
                "session_id": "$99",
                "session_name": "w",
                "session_created": "0",
                "worker_id": "x",
            }
            mock_launch.return_value = {"status": "error", "message": "claude not found"}

            result = await engine.spawn_worker(registered_caller, "sonnet", "/local/repo")

        assert "error" in result
        assert "claude not found" in result["error"]
        mock_kill.assert_awaited_once_with("$99")

    @pytest.mark.asyncio
    async def test_agent_launch_failure_does_not_write_db_row(self, db_path, registered_caller):
        """When agent launch fails, no worker row is written to the DB."""
        with (
            patch("waggle.engine.tmux.clone_or_update_repo_async", new_callable=AsyncMock) as mock_clone,
            patch("waggle.engine.tmux.create_session", new_callable=AsyncMock) as mock_create,
            patch("waggle.engine.tmux.launch_agent_in_pane", new_callable=AsyncMock) as mock_launch,
            patch("waggle.engine.tmux.kill_session", new_callable=AsyncMock),
        ):
            mock_clone.return_value = "/local/repo"
            mock_create.return_value = {
                "status": "success",
                "session_id": "$88",
                "session_name": "w",
                "session_created": "0",
                "worker_id": "x",
            }
            mock_launch.return_value = {"status": "error", "message": "launch failed"}

            await engine.spawn_worker(registered_caller, "sonnet", "/local/repo")

        with connection(db_path) as conn:
            count = conn.execute("SELECT COUNT(*) FROM workers").fetchone()[0]

        assert count == 0


# ---------------------------------------------------------------------------
# list_workers
# ---------------------------------------------------------------------------


class TestListWorkers:
    """Tests for engine.list_workers()."""

    @pytest.mark.asyncio
    async def test_empty_list_when_no_workers(self, db_path, registered_caller):
        """Returns an empty list when caller has no workers."""
        result = await engine.list_workers(registered_caller)
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_workers_for_caller(self, db_path, registered_caller):
        """Returns all workers belonging to the given caller."""
        w1, _, _ = _insert_worker(db_path, caller_id=registered_caller)
        w2, _, _ = _insert_worker(db_path, caller_id=registered_caller)

        result = await engine.list_workers(registered_caller)

        worker_ids = {r["worker_id"] for r in result}
        assert worker_ids == {w1, w2}

    @pytest.mark.asyncio
    async def test_isolates_from_other_callers(self, db_path, registered_caller):
        """Workers belonging to other callers are not returned."""
        await engine.register_caller("other-caller", "local")
        _insert_worker(db_path, caller_id="other-caller")
        my_worker, _, _ = _insert_worker(db_path, caller_id=registered_caller)

        result = await engine.list_workers(registered_caller)

        assert len(result) == 1
        assert result[0]["worker_id"] == my_worker

    @pytest.mark.asyncio
    async def test_returns_all_worker_fields(self, db_path, registered_caller):
        """Each returned worker dict includes expected fields."""
        _insert_worker(db_path, caller_id=registered_caller)

        result = await engine.list_workers(registered_caller)

        assert len(result) == 1
        row = result[0]
        for field in ("worker_id", "caller_id", "session_name", "session_id", "model", "repo", "status"):
            assert field in row


# ---------------------------------------------------------------------------
# check_status
# ---------------------------------------------------------------------------


class TestCheckStatus:
    """Tests for engine.check_status()."""

    @pytest.mark.asyncio
    async def test_success_returns_status_fields(self, db_path, registered_caller):
        """Returns expected fields for a valid caller+worker combination."""
        worker_id, _, _ = _insert_worker(db_path, caller_id=registered_caller)

        result = await engine.check_status(registered_caller, worker_id)

        assert result["worker_id"] == worker_id
        assert result["status"] == "working"
        assert "output_lines" in result
        assert "updated_at" in result
        assert result["pending_relay"] is None

    @pytest.mark.asyncio
    async def test_wrong_caller_id_returns_not_found(self, db_path, registered_caller):
        """Checking status with the wrong caller_id returns worker_not_found."""
        worker_id, _, _ = _insert_worker(db_path, caller_id=registered_caller)

        result = await engine.check_status("wrong-caller", worker_id)

        assert result == {"error": "worker_not_found"}

    @pytest.mark.asyncio
    async def test_nonexistent_worker_returns_not_found(self, db_path, registered_caller):
        """Checking status for a non-existent worker_id returns worker_not_found."""
        result = await engine.check_status(registered_caller, str(uuid.uuid4()))

        assert result == {"error": "worker_not_found"}

    @pytest.mark.asyncio
    async def test_pending_relay_included_when_present(self, db_path, registered_caller):
        """When a pending relay exists, pending_relay is populated in the response."""
        worker_id, _, _ = _insert_worker(db_path, caller_id=registered_caller)
        relay_id = _insert_pending_relay(db_path, worker_id, relay_type="permission", details='{"cmd":"rm"}')

        result = await engine.check_status(registered_caller, worker_id)

        assert result["pending_relay"] is not None
        assert result["pending_relay"]["relay_id"] == relay_id
        assert result["pending_relay"]["relay_type"] == "permission"
        assert result["pending_relay"]["details"] == '{"cmd":"rm"}'

    @pytest.mark.asyncio
    async def test_no_pending_relay_when_resolved(self, db_path, registered_caller):
        """Resolved relays (status != 'pending') do not appear in pending_relay."""
        worker_id, _, _ = _insert_worker(db_path, caller_id=registered_caller)
        # Insert a relay but mark it as resolved
        relay_id = str(uuid.uuid4())
        with connection(db_path) as conn:
            conn.execute(
                """
                INSERT INTO pending_relays
                    (relay_id, worker_id, relay_type, details, status)
                VALUES (?, ?, 'ask', '{}', 'resolved')
                """,
                (relay_id, worker_id),
            )

        result = await engine.check_status(registered_caller, worker_id)

        assert result["pending_relay"] is None


# ---------------------------------------------------------------------------
# get_output
# ---------------------------------------------------------------------------


class TestGetOutput:
    """Tests for engine.get_output()."""

    @pytest.mark.asyncio
    async def test_success_returns_lines(self, db_path, registered_caller):
        """Successful capture returns {worker_id, lines}."""
        worker_id, session_id, _ = _insert_worker(db_path, caller_id=registered_caller)

        with patch("waggle.engine.tmux.capture_pane", new_callable=AsyncMock) as mock_capture:
            mock_capture.return_value = {"status": "success", "content": "line1\nline2"}

            result = await engine.get_output(registered_caller, worker_id)

        assert result == {"worker_id": worker_id, "lines": "line1\nline2"}
        mock_capture.assert_awaited_once_with(session_id, scrollback=200)

    @pytest.mark.asyncio
    async def test_wrong_caller_returns_not_found(self, db_path, registered_caller):
        """Wrong caller_id returns worker_not_found without calling tmux."""
        worker_id, _, _ = _insert_worker(db_path, caller_id=registered_caller)

        with patch("waggle.engine.tmux.capture_pane", new_callable=AsyncMock) as mock_capture:
            result = await engine.get_output("wrong-caller", worker_id)

        assert result == {"error": "worker_not_found"}
        mock_capture.assert_not_called()

    @pytest.mark.asyncio
    async def test_nonexistent_worker_returns_not_found(self, db_path, registered_caller):
        """Non-existent worker_id returns worker_not_found."""
        result = await engine.get_output(registered_caller, str(uuid.uuid4()))
        assert result == {"error": "worker_not_found"}

    @pytest.mark.asyncio
    async def test_capture_failure_returns_error(self, db_path, registered_caller):
        """capture_pane failure propagates as an error."""
        worker_id, _, _ = _insert_worker(db_path, caller_id=registered_caller)

        with patch("waggle.engine.tmux.capture_pane", new_callable=AsyncMock) as mock_capture:
            mock_capture.return_value = {"status": "error", "message": "no such pane"}

            result = await engine.get_output(registered_caller, worker_id)

        assert "error" in result
        assert "no such pane" in result["error"]

    @pytest.mark.asyncio
    async def test_custom_scrollback_passed_through(self, db_path, registered_caller):
        """scrollback parameter is forwarded to capture_pane."""
        worker_id, session_id, _ = _insert_worker(db_path, caller_id=registered_caller)

        with patch("waggle.engine.tmux.capture_pane", new_callable=AsyncMock) as mock_capture:
            mock_capture.return_value = {"status": "success", "content": ""}

            await engine.get_output(registered_caller, worker_id, scrollback=500)

        mock_capture.assert_awaited_once_with(session_id, scrollback=500)


# ---------------------------------------------------------------------------
# terminate_worker
# ---------------------------------------------------------------------------


class TestTerminateWorker:
    """Tests for engine.terminate_worker()."""

    @pytest.mark.asyncio
    async def test_success_returns_terminated_true(self, db_path, registered_caller):
        """Successful termination returns {worker_id, terminated: True}."""
        worker_id, session_id, _ = _insert_worker(db_path, caller_id=registered_caller)

        with patch("waggle.engine.tmux.kill_session", new_callable=AsyncMock) as mock_kill:
            mock_kill.return_value = {"status": "success"}

            result = await engine.terminate_worker(registered_caller, worker_id)

        assert result == {"worker_id": worker_id, "terminated": True}
        mock_kill.assert_awaited_once_with(session_id)

    @pytest.mark.asyncio
    async def test_success_deletes_db_row(self, db_path, registered_caller):
        """After successful termination, the worker row is removed from the DB."""
        worker_id, _, _ = _insert_worker(db_path, caller_id=registered_caller)

        with patch("waggle.engine.tmux.kill_session", new_callable=AsyncMock):
            await engine.terminate_worker(registered_caller, worker_id)

        with connection(db_path) as conn:
            row = conn.execute(
                "SELECT * FROM workers WHERE worker_id = ?",
                (worker_id,),
            ).fetchone()

        assert row is None

    @pytest.mark.asyncio
    async def test_wrong_caller_returns_not_found(self, db_path, registered_caller):
        """Wrong caller_id returns worker_not_found without killing session."""
        worker_id, _, _ = _insert_worker(db_path, caller_id=registered_caller)

        with patch("waggle.engine.tmux.kill_session", new_callable=AsyncMock) as mock_kill:
            result = await engine.terminate_worker("wrong-caller", worker_id)

        assert result == {"error": "worker_not_found"}
        mock_kill.assert_not_called()

    @pytest.mark.asyncio
    async def test_nonexistent_worker_returns_not_found(self, db_path, registered_caller):
        """Non-existent worker_id returns worker_not_found."""
        with patch("waggle.engine.tmux.kill_session", new_callable=AsyncMock) as mock_kill:
            result = await engine.terminate_worker(registered_caller, str(uuid.uuid4()))

        assert result == {"error": "worker_not_found"}
        mock_kill.assert_not_called()

    @pytest.mark.asyncio
    async def test_wrong_caller_does_not_delete_row(self, db_path, registered_caller):
        """When caller check fails, the worker row is NOT deleted from the DB."""
        worker_id, _, _ = _insert_worker(db_path, caller_id=registered_caller)

        with patch("waggle.engine.tmux.kill_session", new_callable=AsyncMock):
            await engine.terminate_worker("wrong-caller", worker_id)

        with connection(db_path) as conn:
            row = conn.execute(
                "SELECT * FROM workers WHERE worker_id = ?",
                (worker_id,),
            ).fetchone()

        assert row is not None
