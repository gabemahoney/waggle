"""Tests for waggle CLI relay handlers: _handle_permission_request and _handle_ask_relay."""

import io
import json
import uuid
from subprocess import CompletedProcess
from unittest.mock import MagicMock, patch

import pytest

from waggle.cli import _handle_ask_relay, _handle_permission_request
from waggle.database import connection, init_schema


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    """Temp SQLite DB wired into CLI config via monkeypatch."""
    path = str(tmp_path / "test.db")
    init_schema(path)
    monkeypatch.setattr("waggle.config.get_db_path", lambda: path)
    monkeypatch.setattr(
        "waggle.config.get_config",
        lambda: {
            "database_path": path,
            "relay_timeout_seconds": 60,
        },
    )
    return path


@pytest.fixture
def worker_id(db_path):
    """Pre-insert a worker row; return its worker_id."""
    wid = str(uuid.uuid4())
    with connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO workers
                (worker_id, caller_id, session_name, session_id, model, repo, status)
            VALUES (?, 'test-caller', 'test-session', '$1', 'sonnet', '/repo', 'working')
            """,
            (wid,),
        )
    return wid


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _tmux_mock(worker_id):
    """subprocess.run mock that returns WAGGLE_WORKER_ID=<worker_id>."""
    mock = MagicMock()
    mock.return_value = CompletedProcess(
        args=[], returncode=0,
        stdout=f"WAGGLE_WORKER_ID={worker_id}\n",
        stderr="",
    )
    return mock


def _no_id_tmux_mock():
    """subprocess.run mock that simulates missing WAGGLE_WORKER_ID."""
    mock = MagicMock()
    mock.return_value = CompletedProcess(
        args=[], returncode=1,
        stdout="-WAGGLE_WORKER_ID\n",
        stderr="",
    )
    return mock


def _resolve_on_sleep(db_path, worker_id, response):
    """Return a side_effect for time.sleep that resolves the worker's pending relay."""
    def _side_effect(duration):
        with connection(db_path) as conn:
            conn.execute(
                """
                UPDATE pending_relays
                SET status = 'resolved', response = ?
                WHERE worker_id = ? AND status = 'pending'
                """,
                (response, worker_id),
            )
    return _side_effect


PERM_HOOK_DATA = json.dumps({
    "tool_name": "Bash",
    "tool_input": {"command": "rm -rf /"},
})

ASK_HOOK_DATA = json.dumps({
    "tool_input": {"question": "What should I do?"},
})


# ---------------------------------------------------------------------------
# _handle_permission_request
# ---------------------------------------------------------------------------


class TestHandlePermissionRequest:
    """Tests for the PermissionRequest CLI hook handler."""

    def test_no_worker_id_exits_0_no_db_changes(self, db_path):
        """No WAGGLE_WORKER_ID in tmux env → exits 0, no DB changes."""
        with patch("waggle.cli.subprocess.run", _no_id_tmux_mock()):
            with patch("sys.stdin", io.StringIO(PERM_HOOK_DATA)):
                with pytest.raises(SystemExit) as exc_info:
                    _handle_permission_request(None)

        assert exc_info.value.code == 0
        with connection(db_path) as conn:
            count = conn.execute("SELECT COUNT(*) FROM pending_relays").fetchone()[0]
        assert count == 0

    def test_valid_flow_creates_pending_relay_and_sets_worker_status(self, db_path, worker_id):
        """Valid flow: pending_relays row created (type=permission), workers.status=check_permission."""
        mock_sleep = MagicMock(side_effect=_resolve_on_sleep(db_path, worker_id, "allow"))

        with patch("waggle.cli.subprocess.run", _tmux_mock(worker_id)):
            with patch("sys.stdin", io.StringIO(PERM_HOOK_DATA)):
                with patch("waggle.cli.time.sleep", mock_sleep):
                    with pytest.raises(SystemExit):
                        _handle_permission_request(None)

        with connection(db_path) as conn:
            relay = conn.execute(
                "SELECT relay_type FROM pending_relays WHERE worker_id = ?",
                (worker_id,),
            ).fetchone()
            worker = conn.execute(
                "SELECT status FROM workers WHERE worker_id = ?",
                (worker_id,),
            ).fetchone()

        assert relay is not None
        assert relay["relay_type"] == "permission"
        assert worker["status"] == "check_permission"

    def test_poll_resolved_allow_prints_allow_json(self, db_path, worker_id, capsys):
        """Poll finds resolved+allow → prints allow JSON."""
        mock_sleep = MagicMock(side_effect=_resolve_on_sleep(db_path, worker_id, "allow"))

        with patch("waggle.cli.subprocess.run", _tmux_mock(worker_id)):
            with patch("sys.stdin", io.StringIO(PERM_HOOK_DATA)):
                with patch("waggle.cli.time.sleep", mock_sleep):
                    with pytest.raises(SystemExit) as exc_info:
                        _handle_permission_request(None)

        assert exc_info.value.code == 0
        output = json.loads(capsys.readouterr().out)
        assert output["hookSpecificOutput"]["hookEventName"] == "PermissionRequest"
        assert output["hookSpecificOutput"]["decision"]["behavior"] == "allow"

    def test_poll_resolved_deny_prints_deny_json_with_message(self, db_path, worker_id, capsys):
        """Poll finds resolved+deny → prints deny JSON with message."""
        mock_sleep = MagicMock(side_effect=_resolve_on_sleep(db_path, worker_id, "deny"))

        with patch("waggle.cli.subprocess.run", _tmux_mock(worker_id)):
            with patch("sys.stdin", io.StringIO(PERM_HOOK_DATA)):
                with patch("waggle.cli.time.sleep", mock_sleep):
                    with pytest.raises(SystemExit) as exc_info:
                        _handle_permission_request(None)

        assert exc_info.value.code == 0
        output = json.loads(capsys.readouterr().out)
        decision = output["hookSpecificOutput"]["decision"]
        assert decision["behavior"] == "deny"
        assert decision["message"] == "Denied by orchestrator"

    def test_timeout_prints_deny_and_marks_relay_timeout(self, db_path, worker_id, capsys):
        """Timeout → prints deny JSON, relay status=timeout."""
        with patch("waggle.cli.subprocess.run", _tmux_mock(worker_id)):
            with patch("sys.stdin", io.StringIO(PERM_HOOK_DATA)):
                with patch("waggle.cli.time.sleep"):  # no-op
                    with patch("waggle.cli.time.monotonic", side_effect=[0.0, 3601.0]):
                        with pytest.raises(SystemExit) as exc_info:
                            _handle_permission_request(None)

        assert exc_info.value.code == 0
        output = json.loads(capsys.readouterr().out)
        assert output["hookSpecificOutput"]["decision"]["behavior"] == "deny"

        with connection(db_path) as conn:
            relay = conn.execute(
                "SELECT status FROM pending_relays WHERE worker_id = ?",
                (worker_id,),
            ).fetchone()
        assert relay["status"] == "timeout"


# ---------------------------------------------------------------------------
# _handle_ask_relay
# ---------------------------------------------------------------------------


class TestHandleAskRelay:
    """Tests for the AskUserQuestion PreToolUse hook handler."""

    def test_no_worker_id_exits_0_no_db_changes(self, db_path):
        """No WAGGLE_WORKER_ID → exits 0, no DB changes."""
        with patch("waggle.cli.subprocess.run", _no_id_tmux_mock()):
            with patch("sys.stdin", io.StringIO(ASK_HOOK_DATA)):
                with pytest.raises(SystemExit) as exc_info:
                    _handle_ask_relay(None)

        assert exc_info.value.code == 0
        with connection(db_path) as conn:
            count = conn.execute("SELECT COUNT(*) FROM pending_relays").fetchone()[0]
        assert count == 0

    def test_valid_flow_creates_ask_relay_and_sets_worker_status(self, db_path, worker_id):
        """Valid flow: pending_relays row created (type=ask), workers.status=ask_user."""
        mock_sleep = MagicMock(side_effect=_resolve_on_sleep(db_path, worker_id, "It's fine."))

        with patch("waggle.cli.subprocess.run", _tmux_mock(worker_id)):
            with patch("sys.stdin", io.StringIO(ASK_HOOK_DATA)):
                with patch("waggle.cli.time.sleep", mock_sleep):
                    with pytest.raises(SystemExit):
                        _handle_ask_relay(None)

        with connection(db_path) as conn:
            relay = conn.execute(
                "SELECT relay_type FROM pending_relays WHERE worker_id = ?",
                (worker_id,),
            ).fetchone()
            worker = conn.execute(
                "SELECT status FROM workers WHERE worker_id = ?",
                (worker_id,),
            ).fetchone()

        assert relay is not None
        assert relay["relay_type"] == "ask"
        assert worker["status"] == "ask_user"

    def test_poll_resolved_prints_allow_with_answer(self, db_path, worker_id, capsys):
        """Poll finds resolved → prints allow JSON with question→answer mapping."""
        answer = "Yes, proceed!"
        mock_sleep = MagicMock(side_effect=_resolve_on_sleep(db_path, worker_id, answer))

        with patch("waggle.cli.subprocess.run", _tmux_mock(worker_id)):
            with patch("sys.stdin", io.StringIO(ASK_HOOK_DATA)):
                with patch("waggle.cli.time.sleep", mock_sleep):
                    with pytest.raises(SystemExit) as exc_info:
                        _handle_ask_relay(None)

        assert exc_info.value.code == 0
        output = json.loads(capsys.readouterr().out)
        hso = output["hookSpecificOutput"]
        assert hso["hookEventName"] == "PreToolUse"
        assert hso["permissionDecision"] == "allow"
        assert hso["updatedInput"]["answers"]["What should I do?"] == answer

    def test_timeout_prints_deny(self, db_path, worker_id, capsys):
        """Timeout → prints deny JSON (no answers key)."""
        with patch("waggle.cli.subprocess.run", _tmux_mock(worker_id)):
            with patch("sys.stdin", io.StringIO(ASK_HOOK_DATA)):
                with patch("waggle.cli.time.sleep"):  # no-op
                    with patch("waggle.cli.time.monotonic", side_effect=[0.0, 3601.0]):
                        with pytest.raises(SystemExit) as exc_info:
                            _handle_ask_relay(None)

        assert exc_info.value.code == 0
        output = json.loads(capsys.readouterr().out)
        hso = output["hookSpecificOutput"]
        assert hso["hookEventName"] == "PreToolUse"
        assert hso["permissionDecision"] == "deny"
        assert "updatedInput" not in hso

        with connection(db_path) as conn:
            relay = conn.execute(
                "SELECT status FROM pending_relays WHERE worker_id = ?",
                (worker_id,),
            ).fetchone()
        assert relay["status"] == "timeout"
