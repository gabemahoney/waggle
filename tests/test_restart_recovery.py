"""Tests for src/waggle/recovery.py — restart_recovery and helpers."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from waggle.database import connection, init_schema
from waggle.recovery import (
    _enforce_permissions,
    _enqueue_dead_notification,
    _timeout_pending_relays,
    restart_recovery,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def db(tmp_path):
    db_path = str(tmp_path / "state.db")
    init_schema(db_path)
    return db_path


def _insert_worker(db_path, worker_id, caller_id, session_id, status="working"):
    with connection(db_path) as conn:
        conn.execute(
            "INSERT INTO workers (worker_id, caller_id, session_name, session_id, model, repo, status) "
            "VALUES (?, ?, ?, ?, 'sonnet', '/repo', ?)",
            (worker_id, caller_id, f"waggle-{worker_id[:8]}", session_id, status),
        )


def _make_mock_queue():
    q = MagicMock()
    q.put = MagicMock()
    return q


# ---------------------------------------------------------------------------
# Test: alive worker gets MCP reconnect
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_alive_worker_gets_mcp_reconnect(db):
    _insert_worker(db, "worker-alive-1", "caller-1", "sess-alive-1")
    q = _make_mock_queue()

    with patch("waggle.recovery._session_alive", return_value=True), \
         patch("waggle.recovery._send_mcp_reconnect", new_callable=AsyncMock) as mock_reconnect, \
         patch("waggle.recovery._enforce_permissions"):
        result = await restart_recovery(q, db)

    mock_reconnect.assert_called_once_with("sess-alive-1")
    assert result["alive"] == 1
    assert result["dead"] == 0


# ---------------------------------------------------------------------------
# Test: dead worker is marked done in DB
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dead_worker_marked_done(db):
    _insert_worker(db, "worker-dead-1", "caller-1", "sess-dead-1")
    q = _make_mock_queue()

    with patch("waggle.recovery._session_alive", return_value=False), \
         patch("waggle.recovery._enforce_permissions"):
        result = await restart_recovery(q, db)

    with connection(db) as conn:
        row = conn.execute(
            "SELECT status FROM workers WHERE worker_id = ?", ("worker-dead-1",)
        ).fetchone()

    assert row["status"] == "done"
    assert result["dead"] == 1
    assert result["alive"] == 0


# ---------------------------------------------------------------------------
# Test: dead worker CMA notification enqueued with correct payload
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dead_worker_cma_notification_enqueued(db):
    _insert_worker(db, "worker-dead-2", "caller-2", "sess-dead-2")
    q = _make_mock_queue()

    with patch("waggle.recovery._session_alive", return_value=False), \
         patch("waggle.recovery._enforce_permissions"):
        await restart_recovery(q, db)

    q.put.assert_called_once()
    raw = q.put.call_args[0][0]
    data = json.loads(raw)
    assert data["caller_id"] == "caller-2"
    assert data["payload"]["type"] == "worker_state_change"
    assert data["payload"]["status"] == "done"
    assert data["payload"]["worker_id"] == "worker-dead-2"


# ---------------------------------------------------------------------------
# Test: dead worker pending relays timed out
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dead_worker_pending_relays_timed_out(db):
    _insert_worker(db, "worker-dead-3", "caller-3", "sess-dead-3")
    with connection(db) as conn:
        conn.execute(
            "INSERT INTO pending_relays (relay_id, worker_id, relay_type, details, status) "
            "VALUES (?, ?, ?, ?, ?)",
            ("relay-dead-1", "worker-dead-3", "ask", "question?", "pending"),
        )
    q = _make_mock_queue()

    with patch("waggle.recovery._session_alive", return_value=False), \
         patch("waggle.recovery._enforce_permissions"):
        result = await restart_recovery(q, db)

    with connection(db) as conn:
        row = conn.execute(
            "SELECT status FROM pending_relays WHERE relay_id = ?", ("relay-dead-1",)
        ).fetchone()

    assert row["status"] == "timeout"
    assert result["relays_timed_out"] == 1


# ---------------------------------------------------------------------------
# Test: alive worker pending relays left unchanged
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_alive_worker_pending_relays_unchanged(db):
    _insert_worker(db, "worker-alive-2", "caller-4", "sess-alive-2")
    with connection(db) as conn:
        conn.execute(
            "INSERT INTO pending_relays (relay_id, worker_id, relay_type, details, status) "
            "VALUES (?, ?, ?, ?, ?)",
            ("relay-alive-1", "worker-alive-2", "ask", "still waiting?", "pending"),
        )
    q = _make_mock_queue()

    with patch("waggle.recovery._session_alive", return_value=True), \
         patch("waggle.recovery._send_mcp_reconnect", new_callable=AsyncMock), \
         patch("waggle.recovery._enforce_permissions"):
        await restart_recovery(q, db)

    with connection(db) as conn:
        row = conn.execute(
            "SELECT status FROM pending_relays WHERE relay_id = ?", ("relay-alive-1",)
        ).fetchone()

    assert row["status"] == "pending"


# ---------------------------------------------------------------------------
# Test: file permissions enforced
# ---------------------------------------------------------------------------


def test_file_permissions_enforced(tmp_path):
    waggle_dir = tmp_path / ".waggle"
    waggle_dir.mkdir(mode=0o777)
    test_file = waggle_dir / "state.db"
    test_file.write_text("data")
    test_file.chmod(0o644)

    with patch.object(Path, "home", return_value=tmp_path):
        _enforce_permissions()

    assert oct(waggle_dir.stat().st_mode & 0o777) == oct(0o700)
    assert oct(test_file.stat().st_mode & 0o777) == oct(0o600)


# ---------------------------------------------------------------------------
# Test: no workers returns all-zeros result
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_workers_returns_zeros(db):
    q = _make_mock_queue()
    with patch("waggle.recovery._enforce_permissions"):
        result = await restart_recovery(q, db)

    assert result == {"alive": 0, "dead": 0, "relays_timed_out": 0}
    q.put.assert_not_called()


# ---------------------------------------------------------------------------
# Test: multiple workers — counts correct
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_multiple_workers_mixed(db):
    _insert_worker(db, "worker-m1", "caller-5", "sess-m1")
    _insert_worker(db, "worker-m2", "caller-5", "sess-m2")
    _insert_worker(db, "worker-m3", "caller-5", "sess-m3")
    q = _make_mock_queue()

    def _alive(session_id):
        # m1 and m2 alive, m3 dead
        return session_id != "sess-m3"

    with patch("waggle.recovery._session_alive", side_effect=_alive), \
         patch("waggle.recovery._send_mcp_reconnect", new_callable=AsyncMock), \
         patch("waggle.recovery._enforce_permissions"):
        result = await restart_recovery(q, db)

    assert result["alive"] == 2
    assert result["dead"] == 1
    assert result["relays_timed_out"] == 0
