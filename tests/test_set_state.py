"""Unit tests for waggle set-state CLI hook (_handle_set_state)."""

import argparse
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from waggle.cli import _handle_set_state
from waggle.database import connection, init_schema


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    path = str(tmp_path / "test.db")
    init_schema(path)
    monkeypatch.setattr("waggle.config.get_db_path", lambda: path)
    return path


@pytest.fixture
def worker_in_db(db_path):
    """Insert a test worker row."""
    with connection(db_path) as conn:
        conn.execute(
            "INSERT INTO workers (worker_id, caller_id, session_name, session_id, model, repo, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("test-worker-uuid", "test-caller", "waggle-test", "$1", "sonnet", "/repo", "working"),
        )
    return "test-worker-uuid"


def _args(delete=False):
    args = argparse.Namespace()
    args.delete = delete
    return args


def _mock_tmux_result(output):
    result = MagicMock()
    result.stdout = output
    return result


# ---------------------------------------------------------------------------
# 1. WAGGLE_WORKER_ID read from tmux env
# ---------------------------------------------------------------------------

class TestWorkerIdExtraction:
    def test_extracts_worker_id_from_tmux_env(self, db_path, worker_in_db):
        """Verify worker_id is extracted correctly from tmux show-environment output."""
        with patch("subprocess.run", return_value=_mock_tmux_result("WAGGLE_WORKER_ID=test-worker-uuid\n")):
            with patch("waggle.tmux._capture_pane_sync", return_value={"status": "success", "content": "done output\n>"}):
                with patch("waggle.state_parser.parse", return_value=("done", None)):
                    with pytest.raises(SystemExit) as exc:
                        _handle_set_state(_args())
        assert exc.value.code == 0
        # Verify the row was updated (state updated from working to done)
        with connection(db_path) as conn:
            row = conn.execute(
                "SELECT status FROM workers WHERE worker_id = ?", ("test-worker-uuid",)
            ).fetchone()
        assert row["status"] == "done"


# ---------------------------------------------------------------------------
# 2. No-op when WAGGLE_WORKER_ID absent
# ---------------------------------------------------------------------------

class TestNoOpWhenWorkerIdAbsent:
    def test_exits_zero_on_empty_output(self, db_path):
        """Empty tmux output → exits 0 without touching DB."""
        with patch("subprocess.run", return_value=_mock_tmux_result("")):
            with pytest.raises(SystemExit) as exc:
                _handle_set_state(_args())
        assert exc.value.code == 0

    def test_exits_zero_on_unset_marker(self, db_path):
        """-WAGGLE_WORKER_ID (unset marker) → exits 0."""
        with patch("subprocess.run", return_value=_mock_tmux_result("-WAGGLE_WORKER_ID")):
            with pytest.raises(SystemExit) as exc:
                _handle_set_state(_args())
        assert exc.value.code == 0

    def test_exits_zero_on_subprocess_exception(self, db_path):
        """subprocess.run raising an exception → exits 0."""
        with patch("subprocess.run", side_effect=OSError("tmux not found")):
            with pytest.raises(SystemExit) as exc:
                _handle_set_state(_args())
        assert exc.value.code == 0

    def test_exits_zero_when_no_equals_in_output(self, db_path):
        """Output with no '=' → exits 0."""
        with patch("subprocess.run", return_value=_mock_tmux_result("WAGGLE_WORKER_ID")):
            with pytest.raises(SystemExit) as exc:
                _handle_set_state(_args())
        assert exc.value.code == 0

    def test_exits_zero_when_value_is_empty(self, db_path):
        """WAGGLE_WORKER_ID= (empty value) → exits 0."""
        with patch("subprocess.run", return_value=_mock_tmux_result("WAGGLE_WORKER_ID=")):
            with pytest.raises(SystemExit) as exc:
                _handle_set_state(_args())
        assert exc.value.code == 0


# ---------------------------------------------------------------------------
# 3. --delete mode
# ---------------------------------------------------------------------------

class TestDeleteMode:
    def test_delete_removes_worker_row(self, db_path, worker_in_db):
        """Pre-inserted worker row is deleted when args.delete=True."""
        with patch("subprocess.run", return_value=_mock_tmux_result("WAGGLE_WORKER_ID=test-worker-uuid\n")):
            with pytest.raises(SystemExit) as exc:
                _handle_set_state(_args(delete=True))
        assert exc.value.code == 0
        with connection(db_path) as conn:
            row = conn.execute(
                "SELECT worker_id FROM workers WHERE worker_id = ?", ("test-worker-uuid",)
            ).fetchone()
        assert row is None

    def test_delete_exits_zero(self, db_path, worker_in_db):
        """--delete always exits 0."""
        with patch("subprocess.run", return_value=_mock_tmux_result("WAGGLE_WORKER_ID=test-worker-uuid\n")):
            with pytest.raises(SystemExit) as exc:
                _handle_set_state(_args(delete=True))
        assert exc.value.code == 0


# ---------------------------------------------------------------------------
# 4. Normal state update flow
# ---------------------------------------------------------------------------

class TestNormalStateUpdateFlow:
    @pytest.mark.parametrize("parsed_state,expected_db_state", [
        ("working", "working"),
        ("done", "done"),
        ("ask_user", "ask_user"),
        ("check_permission", "check_permission"),
    ])
    def test_updates_worker_status_in_db(self, db_path, worker_in_db, parsed_state, expected_db_state):
        """DB is updated with the parsed status."""
        pane_content = "some pane output"
        with patch("subprocess.run", return_value=_mock_tmux_result("WAGGLE_WORKER_ID=test-worker-uuid\n")):
            with patch("waggle.tmux._capture_pane_sync", return_value={"status": "success", "content": pane_content}):
                with patch("waggle.state_parser.parse", return_value=(parsed_state, None)):
                    with pytest.raises(SystemExit) as exc:
                        _handle_set_state(_args())
        assert exc.value.code == 0
        with connection(db_path) as conn:
            row = conn.execute(
                "SELECT status, output FROM workers WHERE worker_id = ?", ("test-worker-uuid",)
            ).fetchone()
        assert row["status"] == expected_db_state
        assert row["output"] == pane_content

    def test_stores_pane_content_as_output(self, db_path, worker_in_db):
        """Pane content is stored in the output column."""
        pane_content = "Tool use: Bash\nsome long output here"
        with patch("subprocess.run", return_value=_mock_tmux_result("WAGGLE_WORKER_ID=test-worker-uuid\n")):
            with patch("waggle.tmux._capture_pane_sync", return_value={"status": "success", "content": pane_content}):
                with patch("waggle.state_parser.parse", return_value=("working", None)):
                    with pytest.raises(SystemExit):
                        _handle_set_state(_args())
        with connection(db_path) as conn:
            row = conn.execute(
                "SELECT output FROM workers WHERE worker_id = ?", ("test-worker-uuid",)
            ).fetchone()
        assert row["output"] == pane_content


# ---------------------------------------------------------------------------
# 5. unknown → done mapping
# ---------------------------------------------------------------------------

class TestUnknownToDoneMapping:
    def test_unknown_state_stored_as_done(self, db_path, worker_in_db):
        """parse() returning 'unknown' results in 'done' written to DB."""
        with patch("subprocess.run", return_value=_mock_tmux_result("WAGGLE_WORKER_ID=test-worker-uuid\n")):
            with patch("waggle.tmux._capture_pane_sync", return_value={"status": "success", "content": "output"}):
                with patch("waggle.state_parser.parse", return_value=("unknown", None)):
                    with pytest.raises(SystemExit) as exc:
                        _handle_set_state(_args())
        assert exc.value.code == 0
        with connection(db_path) as conn:
            row = conn.execute(
                "SELECT status FROM workers WHERE worker_id = ?", ("test-worker-uuid",)
            ).fetchone()
        assert row["status"] == "done"

    def test_unknown_state_never_written_to_db(self, db_path, worker_in_db):
        """The literal string 'unknown' is never written to the status column."""
        with patch("subprocess.run", return_value=_mock_tmux_result("WAGGLE_WORKER_ID=test-worker-uuid\n")):
            with patch("waggle.tmux._capture_pane_sync", return_value={"status": "success", "content": "output"}):
                with patch("waggle.state_parser.parse", return_value=("unknown", None)):
                    with pytest.raises(SystemExit):
                        _handle_set_state(_args())
        with connection(db_path) as conn:
            row = conn.execute(
                "SELECT status FROM workers WHERE worker_id = ?", ("test-worker-uuid",)
            ).fetchone()
        assert row["status"] != "unknown"


# ---------------------------------------------------------------------------
# 6. Worker not found in DB
# ---------------------------------------------------------------------------

class TestWorkerNotFound:
    def test_exits_zero_when_worker_not_in_db(self, db_path):
        """Valid WAGGLE_WORKER_ID but no matching DB row → exits 0 (graceful no-op)."""
        with patch("subprocess.run", return_value=_mock_tmux_result("WAGGLE_WORKER_ID=nonexistent-uuid\n")):
            with pytest.raises(SystemExit) as exc:
                _handle_set_state(_args())
        assert exc.value.code == 0


# ---------------------------------------------------------------------------
# 7. Capture pane failure
# ---------------------------------------------------------------------------

class TestCapturePaneFailure:
    def test_exits_zero_on_capture_error(self, db_path, worker_in_db):
        """_capture_pane_sync returning status=error → exits 0."""
        with patch("subprocess.run", return_value=_mock_tmux_result("WAGGLE_WORKER_ID=test-worker-uuid\n")):
            with patch("waggle.tmux._capture_pane_sync", return_value={"status": "error", "message": "pane not found"}):
                with pytest.raises(SystemExit) as exc:
                    _handle_set_state(_args())
        assert exc.value.code == 0

    def test_worker_status_unchanged_on_capture_error(self, db_path, worker_in_db):
        """Worker status remains 'working' when capture fails."""
        with patch("subprocess.run", return_value=_mock_tmux_result("WAGGLE_WORKER_ID=test-worker-uuid\n")):
            with patch("waggle.tmux._capture_pane_sync", return_value={"status": "error", "message": "timeout"}):
                with pytest.raises(SystemExit):
                    _handle_set_state(_args())
        with connection(db_path) as conn:
            row = conn.execute(
                "SELECT status FROM workers WHERE worker_id = ?", ("test-worker-uuid",)
            ).fetchone()
        assert row["status"] == "working"
