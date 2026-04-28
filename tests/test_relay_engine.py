"""Tests for relay engine functions: approve_permission and answer_question."""

import asyncio
import uuid

import pytest

from waggle import engine
from waggle.database import connection, init_schema


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    """Temp SQLite DB wired into the engine."""
    path = str(tmp_path / "test.db")
    init_schema(path)
    monkeypatch.setattr("waggle.engine._db_path", lambda: path)
    monkeypatch.setattr(
        "waggle.engine.config.get_config",
        lambda: {
            "database_path": path,
            "max_workers": 3,
            "repos_path": str(tmp_path / "repos"),
            "mcp_worker_port": 8423,
        },
    )
    return path


@pytest.fixture
def registered_caller(db_path):
    """Pre-register a caller."""
    asyncio.run(engine.register_caller("test-caller", "local"))
    return "test-caller"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _insert_worker(db_path, caller_id="test-caller", status="working"):
    """Insert a worker row directly; return worker_id."""
    worker_id = str(uuid.uuid4())
    session_name = f"waggle-{worker_id[:8]}"
    session_id = f"${uuid.uuid4().hex[:4]}"
    with connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO workers
                (worker_id, caller_id, session_name, session_id, model, repo, status)
            VALUES (?, ?, ?, ?, 'sonnet', '/repo', ?)
            """,
            (worker_id, caller_id, session_name, session_id, status),
        )
    return worker_id


def _insert_pending_relay(db_path, worker_id, relay_type="permission", details="{}"):
    """Insert a pending relay row; return relay_id."""
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
# approve_permission
# ---------------------------------------------------------------------------


class TestApprovePermission:
    """Tests for engine.approve_permission()."""

    @pytest.mark.asyncio
    async def test_success_returns_delivered(self, db_path, registered_caller):
        """Worker exists, pending permission relay exists → returns {worker_id, delivered: True}."""
        worker_id = _insert_worker(db_path, caller_id=registered_caller)
        _insert_pending_relay(db_path, worker_id, relay_type="permission")

        result = await engine.approve_permission(registered_caller, worker_id, "allow")

        assert result == {"worker_id": worker_id, "delivered": True}

    @pytest.mark.asyncio
    async def test_success_resolves_relay_with_allow(self, db_path, registered_caller):
        """Allow decision: relay status=resolved, response=allow."""
        worker_id = _insert_worker(db_path, caller_id=registered_caller)
        relay_id = _insert_pending_relay(db_path, worker_id, relay_type="permission")

        await engine.approve_permission(registered_caller, worker_id, "allow")

        with connection(db_path) as conn:
            row = conn.execute(
                "SELECT status, response FROM pending_relays WHERE relay_id = ?",
                (relay_id,),
            ).fetchone()

        assert row["status"] == "resolved"
        assert row["response"] == "allow"

    @pytest.mark.asyncio
    async def test_success_resolves_relay_with_deny(self, db_path, registered_caller):
        """Deny decision: relay status=resolved, response=deny."""
        worker_id = _insert_worker(db_path, caller_id=registered_caller)
        relay_id = _insert_pending_relay(db_path, worker_id, relay_type="permission")

        await engine.approve_permission(registered_caller, worker_id, "deny")

        with connection(db_path) as conn:
            row = conn.execute(
                "SELECT status, response FROM pending_relays WHERE relay_id = ?",
                (relay_id,),
            ).fetchone()

        assert row["status"] == "resolved"
        assert row["response"] == "deny"

    @pytest.mark.asyncio
    async def test_worker_not_found_bad_worker_id(self, db_path, registered_caller):
        """Unknown worker_id → worker_not_found."""
        result = await engine.approve_permission(registered_caller, str(uuid.uuid4()), "allow")
        assert result == {"error": "worker_not_found"}

    @pytest.mark.asyncio
    async def test_worker_not_found_wrong_caller(self, db_path, registered_caller):
        """Wrong caller_id → worker_not_found."""
        worker_id = _insert_worker(db_path, caller_id=registered_caller)
        result = await engine.approve_permission("wrong-caller", worker_id, "allow")
        assert result == {"error": "worker_not_found"}

    @pytest.mark.asyncio
    async def test_no_pending_permission_when_no_relays(self, db_path, registered_caller):
        """Worker exists, no pending relays → no_pending_permission."""
        worker_id = _insert_worker(db_path, caller_id=registered_caller)
        result = await engine.approve_permission(registered_caller, worker_id, "allow")
        assert result == {"error": "no_pending_permission"}

    @pytest.mark.asyncio
    async def test_no_pending_permission_when_ask_relay_exists(self, db_path, registered_caller):
        """An ask relay does not satisfy the permission check."""
        worker_id = _insert_worker(db_path, caller_id=registered_caller)
        _insert_pending_relay(db_path, worker_id, relay_type="ask")

        result = await engine.approve_permission(registered_caller, worker_id, "allow")
        assert result == {"error": "no_pending_permission"}

    @pytest.mark.asyncio
    async def test_resolved_at_is_set_on_success(self, db_path, registered_caller):
        """resolved_at timestamp is set when relay is resolved."""
        worker_id = _insert_worker(db_path, caller_id=registered_caller)
        relay_id = _insert_pending_relay(db_path, worker_id, relay_type="permission")

        await engine.approve_permission(registered_caller, worker_id, "allow")

        with connection(db_path) as conn:
            row = conn.execute(
                "SELECT resolved_at FROM pending_relays WHERE relay_id = ?",
                (relay_id,),
            ).fetchone()

        assert row["resolved_at"] is not None


# ---------------------------------------------------------------------------
# answer_question
# ---------------------------------------------------------------------------


class TestAnswerQuestion:
    """Tests for engine.answer_question()."""

    @pytest.mark.asyncio
    async def test_success_returns_delivered(self, db_path, registered_caller):
        """Worker exists, pending ask relay exists → returns {worker_id, delivered: True}."""
        worker_id = _insert_worker(db_path, caller_id=registered_caller)
        _insert_pending_relay(db_path, worker_id, relay_type="ask")

        result = await engine.answer_question(registered_caller, worker_id, "Yes, proceed.")

        assert result == {"worker_id": worker_id, "delivered": True}

    @pytest.mark.asyncio
    async def test_success_resolves_relay_with_answer(self, db_path, registered_caller):
        """Answer is stored in response, relay status=resolved."""
        worker_id = _insert_worker(db_path, caller_id=registered_caller)
        relay_id = _insert_pending_relay(db_path, worker_id, relay_type="ask")
        answer = "Deploy to staging first."

        await engine.answer_question(registered_caller, worker_id, answer)

        with connection(db_path) as conn:
            row = conn.execute(
                "SELECT status, response FROM pending_relays WHERE relay_id = ?",
                (relay_id,),
            ).fetchone()

        assert row["status"] == "resolved"
        assert row["response"] == answer

    @pytest.mark.asyncio
    async def test_worker_not_found_bad_worker_id(self, db_path, registered_caller):
        """Unknown worker_id → worker_not_found."""
        result = await engine.answer_question(registered_caller, str(uuid.uuid4()), "answer")
        assert result == {"error": "worker_not_found"}

    @pytest.mark.asyncio
    async def test_worker_not_found_wrong_caller(self, db_path, registered_caller):
        """Wrong caller_id → worker_not_found."""
        worker_id = _insert_worker(db_path, caller_id=registered_caller)
        result = await engine.answer_question("wrong-caller", worker_id, "answer")
        assert result == {"error": "worker_not_found"}

    @pytest.mark.asyncio
    async def test_no_pending_question_when_no_relays(self, db_path, registered_caller):
        """Worker exists, no pending relays → no_pending_question."""
        worker_id = _insert_worker(db_path, caller_id=registered_caller)
        result = await engine.answer_question(registered_caller, worker_id, "answer")
        assert result == {"error": "no_pending_question"}

    @pytest.mark.asyncio
    async def test_no_pending_question_when_permission_relay_exists(self, db_path, registered_caller):
        """A permission relay does not satisfy the ask question check."""
        worker_id = _insert_worker(db_path, caller_id=registered_caller)
        _insert_pending_relay(db_path, worker_id, relay_type="permission")

        result = await engine.answer_question(registered_caller, worker_id, "answer")
        assert result == {"error": "no_pending_question"}

    @pytest.mark.asyncio
    async def test_resolved_at_is_set_on_success(self, db_path, registered_caller):
        """resolved_at timestamp is set when relay is resolved."""
        worker_id = _insert_worker(db_path, caller_id=registered_caller)
        relay_id = _insert_pending_relay(db_path, worker_id, relay_type="ask")

        await engine.answer_question(registered_caller, worker_id, "Done!")

        with connection(db_path) as conn:
            row = conn.execute(
                "SELECT resolved_at FROM pending_relays WHERE relay_id = ?",
                (relay_id,),
            ).fetchone()

        assert row["resolved_at"] is not None
