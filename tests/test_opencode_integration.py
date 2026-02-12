"""
Unit tests for OpenCode integration state tracking.

Tests that the OpenCode plugin correctly calls set_state.sh,
which automatically extracts namespace from pwd and session info from tmux.
"""

import subprocess
import sqlite3
import tempfile
import json
import os
import pytest
from pathlib import Path


@pytest.fixture
def hook_dir():
    """Path to hooks directory."""
    return Path(__file__).parent.parent / "hooks"


@pytest.fixture
def set_state_hook(hook_dir):
    """Path to set_state.sh hook."""
    return hook_dir / "set_state.sh"


def run_hook_with_mocked_tmux(
    hook_path: Path,
    state: str,
    db_path: str,
    cwd: str,
    tmux_session: str = "test_session",
    session_id: str = "$999",
    session_created: str = "1234567890"
) -> subprocess.CompletedProcess:
    """Run set_state.sh with mocked tmux and custom config."""
    # Create mock tmux script
    with tempfile.TemporaryDirectory() as mock_dir:
        mock_path = Path(mock_dir)
        
        # Create mock tmux script - use single quotes to prevent shell interpolation
        tmux_mock = mock_path / "tmux"
        tmux_mock.write_text(f"""#!/usr/bin/env bash
if [[ "$1" == "display-message" ]]; then
    case "$3" in
        '#'{{session_name}}'') echo '{tmux_session}' ;;
        '#'{{session_id}}'') echo '{session_id}' ;;
        '#'{{session_created}}'') echo '{session_created}' ;;
        *) echo '{tmux_session}' ;;
    esac
fi
exit 0
""")
        tmux_mock.chmod(0o755)
        
        # Create mock config directory and file
        waggle_dir = mock_path / ".waggle"
        waggle_dir.mkdir()
        config_file = waggle_dir / "config.json"
        config_file.write_text(json.dumps({"database_path": db_path}))
        
        # Prepare environment with mocked PATH and HOME
        env = os.environ.copy()
        env['PATH'] = f"{mock_dir}:{env.get('PATH', '')}"
        env['HOME'] = str(mock_path)
        
        # Run the hook
        result = subprocess.run(
            ["bash", str(hook_path), state],
            capture_output=True,
            text=True,
            cwd=cwd,
            env=env
        )
        
        return result


class TestOpenCodeIntegration:
    """Test OpenCode plugin integration with waggle state database."""

    def test_set_state_builds_correct_key(self, tmp_path, set_state_hook):
        """Test set_state.sh builds composite key from pwd and tmux session info."""
        db_path = str(tmp_path / "test_state.db")
        state = "working"
        
        result = run_hook_with_mocked_tmux(
            set_state_hook,
            state,
            db_path,
            str(tmp_path)
        )
        
        assert result.returncode == 0, f"set_state.sh failed: {result.stderr}"
        
        # Verify database was updated
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT key, repo, status FROM state")
        rows = cursor.fetchall()
        conn.close()
        
        assert len(rows) == 1, "Expected exactly one database entry"
        key, repo, status_value = rows[0]
        assert status_value == state, f"Expected state '{state}', got '{status_value}'"
        assert repo == str(tmp_path), f"Expected repo '{tmp_path}', got '{repo}'"
        
        # Verify key format: name+id+created (no namespace prefix)
        assert "+" in key, f"Key should have name+id+created format: {key}"
        assert key == "test_session+$999+1234567890"

    def test_state_transitions(self, tmp_path, set_state_hook):
        """Test state transitions update database correctly."""
        db_path = str(tmp_path / "test_state.db")
        
        # Transition 1: working
        result = run_hook_with_mocked_tmux(set_state_hook, "working", db_path, str(tmp_path))
        assert result.returncode == 0
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM state")
        assert cursor.fetchone()[0] == "working"
        
        # Transition 2: waiting
        result = run_hook_with_mocked_tmux(set_state_hook, "waiting", db_path, str(tmp_path))
        assert result.returncode == 0
        
        cursor.execute("SELECT status FROM state")
        assert cursor.fetchone()[0] == "waiting"
        
        # Transition 3: back to working
        result = run_hook_with_mocked_tmux(set_state_hook, "working", db_path, str(tmp_path))
        assert result.returncode == 0
        
        cursor.execute("SELECT status FROM state")
        assert cursor.fetchone()[0] == "working"
        
        conn.close()
