"""Integration tests: full relay lifecycle with a real DB.

Tests the complete flow:
  1. Set up DB with a worker and caller
  2. Simulate the CLI inserting a pending relay (direct DB insert)
  3. Call approve_permission / answer_question engine function
  4. Verify the relay is resolved
"""

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
        },
    )
    return path


@pytest.fixture
def setup_worker(db_path):
    """Register a caller and insert a worker; return (caller_id, worker_id)."""
    caller_id = "test-caller"
    asyncio.run(engine.register_caller(caller_id, "local"))

    worker_id = str(uuid.uuid4())
    with connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO workers
                (worker_id, caller_id, session_name, session_id, model, repo, status)
            VALUES (?, ?, 'test-session', '$1', 'sonnet', '/repo', 'working')
            """,
            (worker_id, caller_id),
        )
    return caller_id, worker_id


def _insert_pending_relay(db_path, worker_id, relay_type, details="{}"):
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
# Permission relay lifecycle
# ---------------------------------------------------------------------------


class TestPermissionRelayLifecycle:

    @pytest.mark.asyncio
    async def test_allow_lifecycle(self, db_path, setup_worker):
        """Insert pending permission relay → approve allow → relay resolved with allow."""
        caller_id, worker_id = setup_worker

        relay_id = _insert_pending_relay(
            db_path, worker_id, "permission",
            details='{"tool_name": "Bash", "tool_input": {"command": "ls"}}',
        )

        result = await engine.approve_permission(caller_id, worker_id, "allow")

        assert result == {"worker_id": worker_id, "delivered": True}

        with connection(db_path) as conn:
            row = conn.execute(
                "SELECT status, response, resolved_at FROM pending_relays WHERE relay_id = ?",
                (relay_id,),
            ).fetchone()

        assert row["status"] == "resolved"
        assert row["response"] == "allow"
        assert row["resolved_at"] is not None

    @pytest.mark.asyncio
    async def test_deny_lifecycle(self, db_path, setup_worker):
        """Insert pending permission relay → approve deny → relay resolved with deny."""
        caller_id, worker_id = setup_worker

        relay_id = _insert_pending_relay(db_path, worker_id, "permission")

        result = await engine.approve_permission(caller_id, worker_id, "deny")

        assert result == {"worker_id": worker_id, "delivered": True}

        with connection(db_path) as conn:
            row = conn.execute(
                "SELECT status, response FROM pending_relays WHERE relay_id = ?",
                (relay_id,),
            ).fetchone()

        assert row["status"] == "resolved"
        assert row["response"] == "deny"

    @pytest.mark.asyncio
    async def test_check_status_shows_pending_relay_before_resolution(self, db_path, setup_worker):
        """check_status returns pending_relay details before the relay is resolved."""
        caller_id, worker_id = setup_worker
        relay_id = _insert_pending_relay(
            db_path, worker_id, "permission",
            details='{"tool_name": "Bash", "tool_input": {"command": "rm /tmp/x"}}',
        )

        status = await engine.check_status(caller_id, worker_id)

        assert status["pending_relay"] is not None
        assert status["pending_relay"]["relay_id"] == relay_id
        assert status["pending_relay"]["relay_type"] == "permission"

    @pytest.mark.asyncio
    async def test_check_status_no_pending_relay_after_resolution(self, db_path, setup_worker):
        """check_status shows no pending relay after approve_permission resolves it."""
        caller_id, worker_id = setup_worker
        _insert_pending_relay(db_path, worker_id, "permission")

        await engine.approve_permission(caller_id, worker_id, "allow")

        status = await engine.check_status(caller_id, worker_id)
        assert status["pending_relay"] is None


# ---------------------------------------------------------------------------
# Ask relay lifecycle
# ---------------------------------------------------------------------------


class TestAskRelayLifecycle:

    @pytest.mark.asyncio
    async def test_full_ask_lifecycle(self, db_path, setup_worker):
        """Insert pending ask relay → answer → relay resolved with answer text."""
        caller_id, worker_id = setup_worker

        relay_id = _insert_pending_relay(
            db_path, worker_id, "ask",
            details='{"question": "Should I proceed with the deployment?"}',
        )
        answer = "Yes, proceed during off-peak hours."

        result = await engine.answer_question(caller_id, worker_id, answer)

        assert result == {"worker_id": worker_id, "delivered": True}

        with connection(db_path) as conn:
            row = conn.execute(
                "SELECT status, response, resolved_at FROM pending_relays WHERE relay_id = ?",
                (relay_id,),
            ).fetchone()

        assert row["status"] == "resolved"
        assert row["response"] == answer
        assert row["resolved_at"] is not None

    @pytest.mark.asyncio
    async def test_check_status_shows_pending_ask_before_resolution(self, db_path, setup_worker):
        """check_status returns pending ask relay details before answer_question is called."""
        caller_id, worker_id = setup_worker
        relay_id = _insert_pending_relay(
            db_path, worker_id, "ask",
            details='{"question": "Proceed?"}',
        )

        status = await engine.check_status(caller_id, worker_id)

        assert status["pending_relay"] is not None
        assert status["pending_relay"]["relay_id"] == relay_id
        assert status["pending_relay"]["relay_type"] == "ask"

    @pytest.mark.asyncio
    async def test_check_status_no_pending_relay_after_answer(self, db_path, setup_worker):
        """check_status shows no pending relay after answer_question resolves it."""
        caller_id, worker_id = setup_worker
        _insert_pending_relay(db_path, worker_id, "ask")

        await engine.answer_question(caller_id, worker_id, "Done!")

        status = await engine.check_status(caller_id, worker_id)
        assert status["pending_relay"] is None

    @pytest.mark.asyncio
    async def test_relay_types_are_independent(self, db_path, setup_worker):
        """An ask relay and a permission relay can coexist; each is resolved by its own function."""
        caller_id, worker_id = setup_worker

        perm_relay_id = _insert_pending_relay(db_path, worker_id, "permission")
        ask_relay_id = _insert_pending_relay(db_path, worker_id, "ask")

        # Resolve the ask relay via answer_question
        await engine.answer_question(caller_id, worker_id, "Yes.")

        with connection(db_path) as conn:
            perm_row = conn.execute(
                "SELECT status FROM pending_relays WHERE relay_id = ?", (perm_relay_id,)
            ).fetchone()
            ask_row = conn.execute(
                "SELECT status FROM pending_relays WHERE relay_id = ?", (ask_relay_id,)
            ).fetchone()

        assert perm_row["status"] == "pending"   # untouched
        assert ask_row["status"] == "resolved"   # resolved by answer_question
