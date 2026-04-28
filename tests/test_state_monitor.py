"""Tests for state_monitor.py — _poll, _session_alive, _get_cma_callers,
_notify_cma_callers, _get_pending_relay."""

import json
import logging
from unittest.mock import MagicMock, patch

import pytest

from waggle.database import init_schema, connection
from waggle.queue import MessageEnvelope, MessageType
from waggle.state_monitor import (
    _get_cma_callers,
    _get_pending_relay,
    _poll,
    _session_alive,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _insert_caller(db_path, caller_id, caller_type="cma", cma_session_id="sess-cma-1", unreachable=0):
    with connection(db_path) as conn:
        conn.execute(
            "INSERT INTO callers (caller_id, caller_type, cma_session_id, unreachable)"
            " VALUES (?, ?, ?, ?)",
            (caller_id, caller_type, cma_session_id, unreachable),
        )


def _insert_worker(db_path, worker_id, caller_id, status="working",
                   session_name="my-session", session_id="tmux-sess-1", output=""):
    with connection(db_path) as conn:
        conn.execute(
            "INSERT INTO workers (worker_id, caller_id, session_name, session_id, model, repo, status, output)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (worker_id, caller_id, session_name, session_id, "claude-sonnet", "/repo", status, output),
        )


def _make_mock_queue():
    q = MagicMock()
    q.put = MagicMock()
    q.get = MagicMock()
    return q


# ---------------------------------------------------------------------------
# _session_alive
# ---------------------------------------------------------------------------


class TestSessionAlive:
    def test_session_found_returns_true(self):
        mock_server = MagicMock()
        mock_server.sessions.get.return_value = MagicMock()  # session exists
        with patch("waggle.state_monitor.libtmux.Server", return_value=mock_server):
            assert _session_alive("sess-1") is True

    def test_session_not_found_returns_false(self):
        mock_server = MagicMock()
        mock_server.sessions.get.return_value = None
        with patch("waggle.state_monitor.libtmux.Server", return_value=mock_server):
            assert _session_alive("sess-missing") is False

    def test_exception_returns_true_and_logs_warning(self, caplog):
        with patch("waggle.state_monitor.libtmux.Server", side_effect=RuntimeError("tmux gone")):
            with caplog.at_level(logging.WARNING, logger="waggle.state_monitor"):
                result = _session_alive("sess-err")
        assert result is True
        assert "libtmux session check failed" in caplog.text


# ---------------------------------------------------------------------------
# _get_cma_callers
# ---------------------------------------------------------------------------


class TestGetCmaCallers:
    def test_returns_cma_caller(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        init_schema(db_path)
        _insert_caller(db_path, "cma-caller", caller_type="cma", cma_session_id="s1")

        result = _get_cma_callers(db_path, "cma-caller")
        assert len(result) == 1
        assert result[0]["caller_id"] == "cma-caller"
        assert result[0]["cma_session_id"] == "s1"

    def test_excludes_local_caller(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        init_schema(db_path)
        _insert_caller(db_path, "local-caller", caller_type="local", cma_session_id=None)

        result = _get_cma_callers(db_path, "local-caller")
        assert result == []

    def test_excludes_unreachable_caller(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        init_schema(db_path)
        _insert_caller(db_path, "bad-caller", caller_type="cma", cma_session_id="s2", unreachable=1)

        result = _get_cma_callers(db_path, "bad-caller")
        assert result == []

    def test_returns_empty_for_unknown_caller(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        init_schema(db_path)

        result = _get_cma_callers(db_path, "nobody")
        assert result == []


# ---------------------------------------------------------------------------
# _poll — transition detection
# ---------------------------------------------------------------------------


class TestPollTransitionDetection:
    def _mock_session_alive(self, alive=True):
        return patch("waggle.state_monitor._session_alive", return_value=alive)

    def test_working_to_done_enqueues_outbound(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        init_schema(db_path)
        _insert_caller(db_path, "c1", caller_type="cma", cma_session_id="cma-s1")
        _insert_worker(db_path, "w1", "c1", status="done")

        q = _make_mock_queue()
        known = {"w1": "working"}  # previous state was working

        with self._mock_session_alive(True):
            _poll(q, db_path, known, output_lines=50)

        q.put.assert_called_once()
        raw = q.put.call_args[0][0]
        data = json.loads(raw)
        assert data["caller_id"] == "c1"
        assert data["payload"]["status"] == "done"
        assert data["payload"]["worker_id"] == "w1"

    def test_first_seen_worker_does_not_notify(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        init_schema(db_path)
        _insert_caller(db_path, "c1", caller_type="cma", cma_session_id="cma-s1")
        _insert_worker(db_path, "w1", "c1", status="done")

        q = _make_mock_queue()
        known = {}  # worker not yet seen

        with self._mock_session_alive(True):
            _poll(q, db_path, known, output_lines=50)

        q.put.assert_not_called()
        assert known["w1"] == "done"

    def test_same_status_no_notification(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        init_schema(db_path)
        _insert_caller(db_path, "c1", caller_type="cma", cma_session_id="cma-s1")
        _insert_worker(db_path, "w1", "c1", status="working")

        q = _make_mock_queue()
        known = {"w1": "working"}

        with self._mock_session_alive(True):
            _poll(q, db_path, known, output_lines=50)

        q.put.assert_not_called()

    def test_transition_to_working_does_not_notify(self, tmp_path):
        """working is not in _NOTIFY_STATUSES, so no notification."""
        db_path = str(tmp_path / "test.db")
        init_schema(db_path)
        _insert_caller(db_path, "c1", caller_type="cma", cma_session_id="cma-s1")
        _insert_worker(db_path, "w1", "c1", status="working")

        q = _make_mock_queue()
        known = {"w1": "done"}  # transitioned back somehow

        with self._mock_session_alive(True):
            _poll(q, db_path, known, output_lines=50)

        q.put.assert_not_called()


# ---------------------------------------------------------------------------
# _poll — CMA-only notification
# ---------------------------------------------------------------------------


class TestPollCmaOnlyNotification:
    def _mock_session_alive(self, alive=True):
        return patch("waggle.state_monitor._session_alive", return_value=alive)

    def test_local_caller_does_not_get_notification(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        init_schema(db_path)
        _insert_caller(db_path, "local-c", caller_type="local", cma_session_id=None)
        _insert_worker(db_path, "w2", "local-c", status="done")

        q = _make_mock_queue()
        known = {"w2": "working"}

        with self._mock_session_alive(True):
            _poll(q, db_path, known, output_lines=50)

        q.put.assert_not_called()

    def test_cma_caller_gets_notification(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        init_schema(db_path)
        _insert_caller(db_path, "cma-c", caller_type="cma", cma_session_id="sess-xyz")
        _insert_worker(db_path, "w3", "cma-c", status="done")

        q = _make_mock_queue()
        known = {"w3": "working"}

        with self._mock_session_alive(True):
            _poll(q, db_path, known, output_lines=50)

        q.put.assert_called_once()

    def test_unreachable_caller_not_notified(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        init_schema(db_path)
        _insert_caller(db_path, "dead-c", caller_type="cma", cma_session_id="sess-dead", unreachable=1)
        _insert_worker(db_path, "w4", "dead-c", status="done")

        q = _make_mock_queue()
        known = {"w4": "working"}

        with self._mock_session_alive(True):
            _poll(q, db_path, known, output_lines=50)

        q.put.assert_not_called()


# ---------------------------------------------------------------------------
# _poll — dead session detection
# ---------------------------------------------------------------------------


class TestPollDeadSession:
    def test_dead_session_marks_worker_done_and_notifies(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        init_schema(db_path)
        _insert_caller(db_path, "c1", caller_type="cma", cma_session_id="cma-s1")
        _insert_worker(db_path, "w5", "c1", status="working", session_id="dead-sess")

        q = _make_mock_queue()
        known = {"w5": "working"}

        with patch("waggle.state_monitor._session_alive", return_value=False):
            _poll(q, db_path, known, output_lines=50)

        # Worker should be marked done in DB
        with connection(db_path) as conn:
            row = conn.execute(
                "SELECT status FROM workers WHERE worker_id = ?", ("w5",)
            ).fetchone()
        assert row["status"] == "done"

        # And a notification should have been enqueued
        q.put.assert_called_once()
        raw = q.put.call_args[0][0]
        data = json.loads(raw)
        assert data["payload"]["status"] == "done"

    def test_already_done_worker_session_not_checked(self, tmp_path):
        """Workers already 'done' should skip the session alive check."""
        db_path = str(tmp_path / "test.db")
        init_schema(db_path)
        _insert_caller(db_path, "c1", caller_type="cma", cma_session_id="cma-s1")
        _insert_worker(db_path, "w6", "c1", status="done", session_id="dead-sess")

        q = _make_mock_queue()
        known = {"w6": "working"}

        mock_alive = MagicMock(return_value=False)
        with patch("waggle.state_monitor._session_alive", mock_alive):
            _poll(q, db_path, known, output_lines=50)

        mock_alive.assert_not_called()


# ---------------------------------------------------------------------------
# _poll — pending_relay included in ask_user payload
# ---------------------------------------------------------------------------


class TestPollPendingRelay:
    def test_ask_user_includes_pending_relay(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        init_schema(db_path)
        _insert_caller(db_path, "c1", caller_type="cma", cma_session_id="s1")
        _insert_worker(db_path, "w7", "c1", status="ask_user")

        with connection(db_path) as conn:
            conn.execute(
                "INSERT INTO pending_relays (relay_id, worker_id, relay_type, details, status)"
                " VALUES (?, ?, ?, ?, ?)",
                ("relay-1", "w7", "ask", "Please confirm", "pending"),
            )

        q = _make_mock_queue()
        known = {"w7": "working"}

        with patch("waggle.state_monitor._session_alive", return_value=True):
            _poll(q, db_path, known, output_lines=50)

        q.put.assert_called_once()
        raw = q.put.call_args[0][0]
        data = json.loads(raw)
        pending = data["payload"]["pending_relay"]
        assert pending is not None
        assert pending["relay_id"] == "relay-1"
        assert pending["relay_type"] == "ask"
        assert pending["details"] == "Please confirm"

    def test_done_status_has_null_pending_relay(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        init_schema(db_path)
        _insert_caller(db_path, "c1", caller_type="cma", cma_session_id="s1")
        _insert_worker(db_path, "w8", "c1", status="done")

        q = _make_mock_queue()
        known = {"w8": "working"}

        with patch("waggle.state_monitor._session_alive", return_value=True):
            _poll(q, db_path, known, output_lines=50)

        q.put.assert_called_once()
        raw = q.put.call_args[0][0]
        data = json.loads(raw)
        assert data["payload"]["pending_relay"] is None


# ---------------------------------------------------------------------------
# _get_pending_relay
# ---------------------------------------------------------------------------


class TestGetPendingRelay:
    def test_returns_pending_relay(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        init_schema(db_path)
        with connection(db_path) as conn:
            conn.execute(
                "INSERT INTO pending_relays (relay_id, worker_id, relay_type, details, status)"
                " VALUES (?, ?, ?, ?, ?)",
                ("relay-x", "ww", "permission", "bash ok?", "pending"),
            )

        result = _get_pending_relay(db_path, "ww")
        assert result is not None
        assert result["relay_id"] == "relay-x"
        assert result["relay_type"] == "permission"
        assert result["details"] == "bash ok?"

    def test_returns_none_when_no_relay(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        init_schema(db_path)
        result = _get_pending_relay(db_path, "nonexistent-worker")
        assert result is None

    def test_returns_none_for_resolved_relay(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        init_schema(db_path)
        with connection(db_path) as conn:
            conn.execute(
                "INSERT INTO pending_relays (relay_id, worker_id, relay_type, details, status)"
                " VALUES (?, ?, ?, ?, ?)",
                ("relay-done", "ww2", "ask", "details here", "resolved"),
            )

        result = _get_pending_relay(db_path, "ww2")
        assert result is None
