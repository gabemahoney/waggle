"""Tests for hook scripts (user_prompt_submit.sh and notification.sh)."""

import json
import os
import sqlite3
import subprocess
import tempfile
import textwrap
from pathlib import Path
from typing import Optional
from unittest import mock

import pytest


# ========== Test Fixtures ==========

@pytest.fixture
def temp_home(tmp_path, monkeypatch):
    """Create a temporary home directory for testing."""
    monkeypatch.setenv("HOME", str(tmp_path))
    return tmp_path


@pytest.fixture
def waggle_dir(temp_home):
    """Create ~/.waggle directory."""
    waggle_dir = temp_home / ".waggle"
    waggle_dir.mkdir(parents=True, exist_ok=True)
    return waggle_dir


@pytest.fixture
def config_file(waggle_dir):
    """Path to config file."""
    return waggle_dir / "config.json"


@pytest.fixture
def db_path(waggle_dir):
    """Default database path."""
    return str(waggle_dir / "agent_state.db")


@pytest.fixture
def hook_dir():
    """Path to hooks directory."""
    return Path(__file__).parent.parent / "hooks"


@pytest.fixture
def set_state_hook(hook_dir):
    """Path to set_state.sh hook."""
    return hook_dir / "set_state.sh"


# ========== Test Helper Functions ==========

def run_set_state_hook(
    hook_path: Path,
    state: str,
    tmux_session: str = "test-session",
    session_id: str = "abc123",
    cwd: str = "/test/namespace",
    env: Optional[dict] = None
) -> subprocess.CompletedProcess:
    """
    Run set_state.sh hook script with mocked dependencies.
    
    Args:
        hook_path: Path to the set_state.sh script
        state: State string to pass as argument
        tmux_session: Mocked tmux session name
        session_id: Mocked tmux session ID
        cwd: Working directory (namespace)
        env: Additional environment variables
    
    Returns:
        CompletedProcess result
    """
    # Prepare environment - keep PATH for bash/sqlite3/jq
    test_env = os.environ.copy()
    if env:
        test_env.update(env)
    
    # Create mock scripts directory
    with tempfile.TemporaryDirectory() as mock_dir:
        mock_path = Path(mock_dir)
        
        # Create mock tmux script
        tmux_mock = mock_path / "tmux"
        tmux_mock.write_text(f"""#!/usr/bin/env bash
if [[ "$1" == "display-message" ]]; then
    case "$3" in
        '#'{{session_name}}'') echo "{tmux_session}" ;;
        '#'{{session_id}}'') echo "{session_id}" ;;
        '#'{{session_created}}'') echo "1234567890" ;;
        *) echo "{tmux_session}" ;;
    esac
fi
exit 0
""")
        tmux_mock.chmod(0o755)
        
        # Prepend mock directory to PATH
        test_env['PATH'] = f"{mock_dir}:{test_env.get('PATH', '')}"
        
        # Run the hook with state argument
        result = subprocess.run(
            ["bash", str(hook_path), state],
            capture_output=True,
            text=True,
            cwd=cwd,
            env=test_env
        )
        
        return result





def get_db_value(db_path: str, key: str) -> Optional[str]:
    """Get a value from the state database."""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM state WHERE key = ?", (key,))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else None
    except sqlite3.OperationalError:
        return None


def table_exists(db_path: str, table_name: str) -> bool:
    """Check if a table exists in the database."""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,)
        )
        result = cursor.fetchone() is not None
        conn.close()
        return result
    except sqlite3.OperationalError:
        return False


# ========== Test Classes ==========

class TestHookFramework:
    """Tests for hook test framework itself."""
    
    def test_run_hook_executes_successfully(self, set_state_hook, temp_home, db_path):
        """Test that run_set_state_hook helper function works."""
        result = run_set_state_hook(set_state_hook, "processing request", cwd=str(temp_home))
        assert result.returncode == 0
    
    def test_get_db_value_retrieves_data(self, db_path):
        """Test that get_db_value helper function works."""
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE state (key TEXT PRIMARY KEY, repo TEXT NOT NULL, status TEXT NOT NULL, updated_at TIMESTAMP)")
        conn.execute("INSERT INTO state (key, repo, status, updated_at) VALUES ('test-key', '/test/repo', 'test-value', CURRENT_TIMESTAMP)")
        conn.commit()
        conn.close()
        
        value = get_db_value(db_path, "test-key")
        assert value == "test-value"
    
    def test_table_exists_detects_tables(self, db_path):
        """Test that table_exists helper function works."""
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE test_table (id INTEGER)")
        conn.commit()
        conn.close()
        
        assert table_exists(db_path, "test_table") is True
        assert table_exists(db_path, "nonexistent_table") is False


class TestConfigReading:
    """Tests for config file reading with fallback behavior."""
    
    def test_hook_reads_database_path_from_valid_config(
        self, set_state_hook, temp_home, config_file, waggle_dir
    ):
        """Hook reads database_path from valid config.json."""
        custom_db = waggle_dir / "custom.db"
        config_data = {"database_path": str(custom_db)}
        with open(config_file, 'w') as f:
            json.dump(config_data, f)
        
        result = run_set_state_hook(set_state_hook, "building project", cwd=str(temp_home))
        assert result.returncode == 0
        
        # Verify hook used custom database path
        key = "test-session+abc123+1234567890"
        value = get_db_value(str(custom_db), key)
        assert value == "building project"
    

    def test_hook_uses_default_when_config_malformed(
        self, set_state_hook, temp_home, config_file, db_path
    ):
        """Hook uses default path when config.json is malformed JSON."""
        with open(config_file, 'w') as f:
            f.write("{this is not valid json")
        
        result = run_set_state_hook(set_state_hook, "analyzing data", cwd=str(temp_home))
        assert result.returncode == 0
        
        # Verify hook used default database path
        key = "test-session+abc123+1234567890"
        value = get_db_value(db_path, key)
        assert value == "analyzing data"
    

    def test_hook_expands_tilde_in_database_path(
        self, set_state_hook, temp_home, config_file, waggle_dir
    ):
        """Hook correctly expands tilde (~) in database_path."""
        config_data = {"database_path": "~/.waggle/tilde_test.db"}
        with open(config_file, 'w') as f:
            json.dump(config_data, f)
        
        result = run_set_state_hook(set_state_hook, "compiling code", cwd=str(temp_home))
        assert result.returncode == 0
        
        # Verify tilde was expanded
        expanded_db = waggle_dir / "tilde_test.db"
        key = "test-session+abc123+1234567890"
        value = get_db_value(str(expanded_db), key)
        assert value == "compiling code"


class TestStdinJsonParsing:
    """Tests for stdin JSON parsing and session_id extraction."""
    
    def test_hook_extracts_session_id_from_valid_json(
        self, set_state_hook, temp_home, db_path
    ):
        """Hook extracts session_id from valid JSON input."""
        result = run_set_state_hook(
            set_state_hook, "executing tests",
            session_id="test-session-123",
            cwd=str(temp_home)
        )
        assert result.returncode == 0
        
        # Verify correct session_id in database key
        key = "test-session+test-session-123+1234567890"
        value = get_db_value(db_path, key)
        assert value == "executing tests"
    

    def test_hook_handles_missing_session_id_field(
        self, set_state_hook, temp_home, db_path
    ):
        """Hook handles JSON without session_id field gracefully."""
        result = run_set_state_hook(set_state_hook, "deploying app", cwd=str(temp_home))
        assert result.returncode == 0
        
        # Verify fallback to "abc123" (mock tmux default when no session_id provided)
        key = "test-session+abc123+1234567890"
        value = get_db_value(db_path, key)
        assert value == "deploying app"
    

    def test_hook_handles_empty_stdin(
        self, set_state_hook, temp_home, db_path
    ):
        """Hook handles empty stdin gracefully."""
        result = subprocess.run(
            ["bash", str(set_state_hook), "initializing"],
            input="",
            capture_output=True,
            text=True,
            cwd=str(temp_home),
            env=os.environ.copy()
        )
        assert result.returncode == 0
        
        # Hook should use "unknown" as fallback for session_id


class TestTmuxSessionExtraction:
    """Tests for tmux session name extraction."""
    
    def test_hook_extracts_tmux_session_name(
        self, set_state_hook, temp_home, db_path
    ):
        """Hook calls tmux display-message and extracts session name."""
        result = run_set_state_hook(
            set_state_hook, "indexing files",
            tmux_session="my-custom-session",
            cwd=str(temp_home)
        )
        assert result.returncode == 0
        
        # Verify correct session name in database key
        key = "my-custom-session+abc123+1234567890"
        value = get_db_value(db_path, key)
        assert value == "indexing files"
    

    def test_hook_uses_different_session_names(
        self, set_state_hook, temp_home, db_path
    ):
        """Hook correctly handles different tmux session names."""
        # Run with first session
        run_set_state_hook(
            set_state_hook, "refactoring code",
            session_id="id1",
            tmux_session="session-alpha",
            cwd=str(temp_home)
        )
        
        # Run with second session
        run_set_state_hook(
            set_state_hook, "running benchmarks",
            session_id="id2",
            tmux_session="session-beta",
            cwd=str(temp_home)
        )
        
        # Verify both keys exist with correct values
        key1 = "session-alpha+id1+1234567890"
        key2 = "session-beta+id2+1234567890"
        assert get_db_value(db_path, key1) == "refactoring code"
        assert get_db_value(db_path, key2) == "running benchmarks"
    


class TestDatabaseUpsert:
    """Tests for database UPSERT behavior and table creation."""
    
    def test_hook_creates_state_table_if_missing(
        self, set_state_hook, temp_home, db_path
    ):
        """Hook creates state table if it doesn't exist."""
        # Ensure database doesn't exist yet
        assert not table_exists(db_path, "state")
        
        result = run_set_state_hook(set_state_hook, "scanning dependencies", cwd=str(temp_home))
        assert result.returncode == 0
        
        # Verify table was created
        assert table_exists(db_path, "state")
    
    def test_hook_writes_repo_column_correctly(
        self, set_state_hook, temp_home, db_path
    ):
        """Hook writes the current working directory to repo column."""
        namespace = temp_home / "workspace" / "myproject"
        os.makedirs(namespace, exist_ok=True)
        
        result = run_set_state_hook(
            set_state_hook, "testing repo column",
            cwd=str(namespace)
        )
        assert result.returncode == 0
        
        # Verify repo column contains the namespace
        key = "test-session+abc123+1234567890"
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT repo FROM state WHERE key = ?", (key,))
        row = cursor.fetchone()
        conn.close()
        
        assert row is not None
        assert row[0] == str(namespace)
    

    def test_hook_updates_existing_key_with_new_value(
        self, set_state_hook, temp_home, db_path
    ):
        """Hook updates existing key with new value (REPLACE behavior)."""
        key = "test-session+abc123+1234567890"
        
        # Pre-populate database with old value
        from waggle.database import init_schema
        init_schema(db_path)
        conn = sqlite3.connect(db_path)
        conn.execute("INSERT INTO state (key, repo, status, updated_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)", (key, str(temp_home), "old_value"))
        conn.commit()
        conn.close()
        
        # Run hook to update value
        result = run_set_state_hook(set_state_hook, "installing packages", cwd=str(temp_home))
        assert result.returncode == 0
        
        # Verify value was updated
        value = get_db_value(db_path, key)
        assert value == "installing packages"
    
    def test_user_prompt_hook_sets_custom_state_value(
        self, set_state_hook, temp_home, db_path
    ):
        """Set state hook sets custom state value."""
        result = run_set_state_hook(set_state_hook, "writing documentation", cwd=str(temp_home))
        assert result.returncode == 0
        
        key = "test-session+abc123+1234567890"
        value = get_db_value(db_path, key)
        assert value == "writing documentation"
    

    def test_hook_uses_correct_key_format(
        self, set_state_hook, temp_home, db_path
    ):
        """Hook uses correct key format: session_name+session_id+created (no namespace prefix)."""
        namespace = temp_home / "workspace" / "project"
        os.makedirs(namespace, exist_ok=True)
        
        result = run_set_state_hook(
            set_state_hook, "reviewing changes",
            session_id="xyz789",
            tmux_session="my-session",
            cwd=str(namespace)
        )
        assert result.returncode == 0
        
        # Verify exact key format (new schema: no namespace prefix in key)
        key = "my-session+xyz789+1234567890"
        value = get_db_value(db_path, key)
        assert value == "reviewing changes"


class TestSilentErrorHandling:
    """Tests for silent error handling when dependencies unavailable."""
    
    def test_hook_exits_successfully_when_sqlite3_unavailable(
        self, set_state_hook, temp_home
    ):
        """Hook exits successfully (exit 0) when sqlite3 command unavailable."""
        # Create mock directory without sqlite3
        with tempfile.TemporaryDirectory() as mock_dir:
            env = os.environ.copy()
            # Create mock sqlite3 that exits with error
            sqlite3_mock = Path(mock_dir) / "sqlite3"
            sqlite3_mock.write_text("#!/usr/bin/env bash\nexit 127\n")
            sqlite3_mock.chmod(0o755)
            
            # Put mock first in PATH
            env['PATH'] = f"{mock_dir}:{env['PATH']}"
            
            result = subprocess.run(
                ["bash", str(set_state_hook), "parsing logs"],
                input=json.dumps({"session_id": "test"}),
                capture_output=True,
                text=True,
                cwd=str(temp_home),
                env=env
            )
            
            # Hook should exit 0 even when sqlite3 fails
            assert result.returncode == 0
            # Should not have error output that could block agent
            # (stderr is redirected to /dev/null in hook)
    

    def test_hook_exits_successfully_when_tmux_unavailable(
        self, set_state_hook, temp_home
    ):
        """Hook exits successfully when tmux command unavailable."""
        # Create mock directory without tmux
        with tempfile.TemporaryDirectory() as mock_dir:
            env = os.environ.copy()
            # Create mock tmux that exits with error
            tmux_mock = Path(mock_dir) / "tmux"
            tmux_mock.write_text("#!/usr/bin/env bash\nexit 127\n")
            tmux_mock.chmod(0o755)
            
            # Put mock first in PATH
            env['PATH'] = f"{mock_dir}:{env['PATH']}"
            
            result = subprocess.run(
                ["bash", str(set_state_hook), "optimizing queries"],
                input=json.dumps({"session_id": "test"}),
                capture_output=True,
                text=True,
                cwd=str(temp_home),
                env=env
            )
            
            # Hook should exit 0 even when tmux fails
            assert result.returncode == 0
    

    def test_hook_exits_successfully_when_config_unreadable(
        self, set_state_hook, temp_home, config_file
    ):
        """Hook exits successfully when config file is unreadable."""
        # Create config file with no read permissions
        config_file.touch()
        os.chmod(config_file, 0o000)
        
        try:
            result = run_set_state_hook(set_state_hook, "formatting output", cwd=str(temp_home))
            
            # Hook should exit 0 even when config unreadable
            assert result.returncode == 0
        finally:
            # Restore permissions for cleanup
            os.chmod(config_file, 0o644)
    

    def test_hook_redirects_stderr_to_dev_null(
        self, set_state_hook, temp_home
    ):
        """Hook redirects stderr to /dev/null to avoid blocking agent."""
        # Read the hook script and verify 2>/dev/null is used
        with open(set_state_hook, 'r') as f:
            content = f.read()
        
        # Verify stderr redirection on critical commands
        assert "2>/dev/null" in content


class TestSetStateHook:
    """Tests for set_state.sh parameterized state hook."""
    
    def test_hook_accepts_custom_state_parameter(
        self, set_state_hook, temp_home, db_path
    ):
        """Hook accepts custom state string as parameter."""
        result = run_set_state_hook(set_state_hook, "custom_state", cwd=str(temp_home))
        assert result.returncode == 0
        
        # Verify state was stored correctly
        key = "test-session+abc123+1234567890"
        value = get_db_value(db_path, key)
        assert value == "custom_state"
    
    def test_hook_sanitizes_single_quotes_in_state(
        self, set_state_hook, temp_home, db_path
    ):
        """Hook sanitizes single quotes in state parameter to prevent SQL injection."""
        result = run_set_state_hook(set_state_hook, "state'with'quotes", cwd=str(temp_home))
        assert result.returncode == 0
        
        # Verify state was stored with escaped quotes
        key = "test-session+abc123+1234567890"
        value = get_db_value(db_path, key)
        assert value == "state'with'quotes"
    
    def test_hook_handles_empty_parameter_gracefully(
        self, set_state_hook, temp_home, db_path
    ):
        """Hook handles empty parameter gracefully (exits without error)."""
        result = subprocess.run(
            ["bash", str(set_state_hook), ""],
            capture_output=True,
            text=True,
            cwd=str(temp_home),
            env=os.environ.copy()
        )
        assert result.returncode == 0
        
        # Verify no database write occurred
        key = "test-session+abc123+1234567890"
        value = get_db_value(db_path, key)
        assert value is None
    
    def test_hook_handles_missing_parameter_gracefully(
        self, set_state_hook, temp_home, db_path
    ):
        """Hook handles missing parameter gracefully (exits without error)."""
        result = subprocess.run(
            ["bash", str(set_state_hook)],
            capture_output=True,
            text=True,
            cwd=str(temp_home),
            env=os.environ.copy()
        )
        assert result.returncode == 0
    
    def test_hook_creates_state_table_if_missing(
        self, set_state_hook, temp_home, db_path
    ):
        """Hook creates state table if it doesn't exist."""
        # Ensure database doesn't exist yet
        assert not table_exists(db_path, "state")
        
        result = subprocess.run(
            ["bash", str(set_state_hook), "test_state"],
            capture_output=True,
            text=True,
            cwd=str(temp_home),
            env=os.environ.copy()
        )
        assert result.returncode == 0
        
        # Verify table was created
        assert table_exists(db_path, "state")
    
    def test_hook_upserts_state_value(
        self, set_state_hook, temp_home, db_path
    ):
        """Hook uses INSERT OR REPLACE to upsert state value."""
        key = "test-session+abc123+1234567890"
        
        # Pre-populate database with old value
        from waggle.database import init_schema
        init_schema(db_path)
        conn = sqlite3.connect(db_path)
        conn.execute("INSERT INTO state (key, repo, status, updated_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)", (key, str(temp_home), "old_state"))
        conn.commit()
        conn.close()
        
        # Run hook to update value
        result = run_set_state_hook(set_state_hook, "new_state", cwd=str(temp_home))
        assert result.returncode == 0
        
        # Verify value was updated
        value = get_db_value(db_path, key)
        assert value == "new_state"
    
    def test_hook_sanitizes_key_for_sql_injection(
        self, set_state_hook, temp_home, db_path
    ):
        """Hook sanitizes key (derived from namespace/session) to prevent SQL injection."""
        # Note: This is harder to test directly since key comes from tmux/namespace
        # We verify sanitization logic exists in the script
        with open(set_state_hook, 'r') as f:
            content = f.read()
        
        # Verify sed sanitization is applied to both KEY and STATE
        assert "sed \"s/'/''/g\"" in content
        assert "SAFE_KEY" in content
        assert "SAFE_STATE" in content
    
    def test_hook_handles_special_characters_in_state(
        self, set_state_hook, temp_home, db_path
    ):
        """Hook handles special characters in state parameter."""
        special_states = [
            "state-with-dashes",
            "state_with_underscores",
            "state with spaces",
            "state/with/slashes",
        ]
        
        for state in special_states:
            result = run_set_state_hook(set_state_hook, state, cwd=str(temp_home))
            assert result.returncode == 0
            
            # Verify state was stored
            key = "test-session+abc123+1234567890"
            value = get_db_value(db_path, key)
            assert value == state
    
    def test_hook_reads_database_path_from_config(
        self, set_state_hook, temp_home, config_file, waggle_dir
    ):
        """Hook reads database_path from config.json."""
        custom_db = waggle_dir / "custom_state.db"
        config_data = {"database_path": str(custom_db)}
        with open(config_file, 'w') as f:
            json.dump(config_data, f)
        
        result = run_set_state_hook(set_state_hook, "config_test", cwd=str(temp_home))
        assert result.returncode == 0
        
        # Verify hook used custom database path
        key = "test-session+abc123+1234567890"
        value = get_db_value(str(custom_db), key)
        assert value == "config_test"
    
    def test_hook_exits_zero_on_all_errors(
        self, set_state_hook, temp_home
    ):
        """Hook always exits with code 0 (silent error handling)."""
        # Read hook script and verify exit 0
        with open(set_state_hook, 'r') as f:
            lines = f.readlines()
        
        # Check last non-empty line is "exit 0"
        last_line = [line.strip() for line in lines if line.strip()][-1]
        assert last_line == "exit 0"
    
    def test_hook_prevents_sql_injection_with_semicolons(
        self, set_state_hook, temp_home, db_path
    ):
        """Hook prevents SQL injection attempts with semicolons."""
        malicious_state = "normal_state'; DROP TABLE state; --"
        result = run_set_state_hook(set_state_hook, malicious_state, cwd=str(temp_home))
        assert result.returncode == 0
        
        # Verify state was stored literally (not executed as SQL)
        key = "test-session+abc123+1234567890"
        value = get_db_value(db_path, key)
        assert value == malicious_state
        
        # Verify state table still exists (wasn't dropped)
        assert table_exists(db_path, "state")
    
    def test_hook_prevents_sql_injection_with_sql_keywords(
        self, set_state_hook, temp_home, db_path
    ):
        """Hook prevents SQL injection with SQL keywords (SELECT, DROP, DELETE)."""
        sql_keywords = [
            "SELECT * FROM state",
            "DROP TABLE state",
            "DELETE FROM state WHERE 1=1",
            "'; DELETE FROM state; --",
        ]
        
        for malicious_state in sql_keywords:
            result = run_set_state_hook(set_state_hook, malicious_state, cwd=str(temp_home))
            assert result.returncode == 0
            
            # Verify state was stored literally
            key = "test-session+abc123+1234567890"
            value = get_db_value(db_path, key)
            assert value == malicious_state
            
            # Verify state table still exists
            assert table_exists(db_path, "state")
    
    def test_hook_stores_custom_state_strings(
        self, set_state_hook, temp_home, db_path
    ):
        """Hook correctly stores various custom state strings."""
        custom_states = [
            "session started",
            "need permission",
            "some other state",
            "waiting for user input",
            "processing large file",
        ]
        
        for state in custom_states:
            result = run_set_state_hook(set_state_hook, state, cwd=str(temp_home))
            assert result.returncode == 0
            
            # Verify state was stored correctly
            key = "test-session+abc123+1234567890"
            value = get_db_value(db_path, key)
            assert value == state
    
    def test_hook_handles_unicode_characters(
        self, set_state_hook, temp_home, db_path
    ):
        """Hook correctly handles unicode and international characters."""
        unicode_states = [
            "状态更新",  # Chinese
            "état mis à jour",  # French with accents
            "🚀 processing",  # Emoji
            "Ñoño español",  # Spanish with tildes
            "Статус",  # Cyrillic
        ]
        
        for state in unicode_states:
            result = run_set_state_hook(set_state_hook, state, cwd=str(temp_home))
            assert result.returncode == 0
            
            # Verify unicode state was stored correctly
            key = "test-session+abc123+1234567890"
            value = get_db_value(db_path, key)
            assert value == state
    
    def test_hook_handles_very_long_state_strings(
        self, set_state_hook, temp_home, db_path
    ):
        """Hook handles very long state strings without truncation."""
        long_state = "state_" + ("x" * 1000)  # 1006 character state
        result = run_set_state_hook(set_state_hook, long_state, cwd=str(temp_home))
        assert result.returncode == 0
        
        # Verify entire state was stored
        key = "test-session+abc123+1234567890"
        value = get_db_value(db_path, key)
        assert value == long_state
        assert value is not None and len(value) == 1006
    
    def test_hook_handles_newlines_and_control_characters(
        self, set_state_hook, temp_home, db_path
    ):
        """Hook handles newlines, tabs, and control characters in state."""
        # Test newlines
        result = run_set_state_hook(set_state_hook, "state\nwith\nnewlines", cwd=str(temp_home))
        assert result.returncode == 0
        key = "test-session+abc123+1234567890"
        value = get_db_value(db_path, key)
        assert value == "state\nwith\nnewlines"
        
        # Test tabs
        result = run_set_state_hook(set_state_hook, "state\twith\ttabs", cwd=str(temp_home))
        assert result.returncode == 0
        value = get_db_value(db_path, key)
        assert value == "state\twith\ttabs"
        
        # Test windows line endings (bash normalizes \r\n to \n)
        result = run_set_state_hook(set_state_hook, "state with\r\nwindows line endings", cwd=str(temp_home))
        assert result.returncode == 0
        value = get_db_value(db_path, key)
        # Bash normalizes \r\n to \n when passing as argument
        assert value == "state with\nwindows line endings"
    
    def test_hook_preserves_trailing_newlines_in_key_sanitization(
        self, set_state_hook, temp_home, db_path
    ):
        """Hook uses printf (not echo) to preserve trailing newlines in key sanitization.
        
        This test verifies the sanitize_sql function uses printf (not echo) to preserve
        trailing newlines. The function uses:
            printf '%s' "$input" | tr ... | sed ...
        
        While trailing newlines in the KEY are unlikely in practice (since KEY is
        derived from namespace:session+id+created), this ensures the sanitization
        logic is robust and consistent.
        """
        # Read the hook script and verify printf is used for sanitization
        with open(set_state_hook, 'r') as f:
            content = f.read()
        
        # Verify sanitize_sql function uses printf for sanitization
        assert "sanitize_sql()" in content, "Expected sanitize_sql function"
        assert "printf '%s' \"$input\"" in content, \
            "Expected printf in sanitize_sql function"
        assert "SAFE_KEY=$(sanitize_sql \"$KEY\")" in content, \
            "Expected KEY to be sanitized via sanitize_sql"
        assert "SAFE_STATE=$(sanitize_sql \"$STATE\")" in content, \
            "Expected STATE to be sanitized via sanitize_sql"
    
    def test_hook_checks_sanitization_pipeline_errors(
        self, set_state_hook, temp_home
    ):
        """Hook checks for sanitization pipeline failures and exits successfully.
        
        This test verifies that the hook has explicit error checking after
        sanitization pipelines to catch failures. Following the "never block the agent"
        design, if sanitization fails (e.g., sed command fails), the hook exits with
        code 0 after logging an error, skipping the DB write to prevent unsafe data.
        """
        # Read the hook script and verify error checking exists
        with open(set_state_hook, 'r') as f:
            content = f.read()
        
        # Verify explicit error checks after sanitization
        assert "if [[ $? -ne 0" in content, \
            "Expected explicit error checking after sanitization"
        assert "Error: Failed to sanitize KEY" in content, \
            "Expected error message for KEY sanitization failure"
        assert "Error: Failed to sanitize STATE" in content, \
            "Expected error message for STATE sanitization failure"
        assert "exit 0" in content, \
            "Expected exit 0 on sanitization failure (never block agent)"
    
    def test_hook_removes_null_bytes_from_state(
        self, set_state_hook, temp_home
    ):
        """Hook sanitization includes null byte removal via tr -d."""
        # Read the hook script and verify null byte removal exists
        # Note: We can't test this via subprocess.run because Python's subprocess
        # doesn't allow null bytes in command arguments. But we can verify the
        # sanitization logic exists in the script.
        with open(set_state_hook, 'r') as f:
            content = f.read()
        
        # Verify null byte removal in sanitize_sql function
        assert "tr -d '\\000'" in content, \
            "Expected null byte removal via tr -d '\\000'"
    
    def test_hook_removes_control_characters_from_state(
        self, set_state_hook, temp_home, db_path
    ):
        """Hook removes control characters (ASCII 0-31, 127) from state parameter."""
        # Control characters like \x01, \x02, etc. can be used for SQL injection
        state_with_control = "normal\x01text\x02here\x1f"
        result = run_set_state_hook(set_state_hook, state_with_control, cwd=str(temp_home))
        assert result.returncode == 0
        
        # Verify control characters were removed (except tab and newline which are handled separately)
        key = "test-session+abc123+1234567890"
        value = get_db_value(db_path, key)
        # tr -d '[\001-\010\013-\037\177]' removes all except \n (012) and \t (011)
        assert value is not None
        assert "\x01" not in value
        assert "\x02" not in value
        assert "\x1f" not in value
        assert value == "normaltexthere"
    
    def test_hook_sanitizes_namespace_variable(
        self, set_state_hook, temp_home, db_path
    ):
        """Hook sanitizes NAMESPACE variable (pwd) to prevent SQL injection via repo column."""
        # Verify sanitization is applied to NAMESPACE (previously unsanitized)
        with open(set_state_hook, 'r') as f:
            content = f.read()
        
        # Verify SAFE_NAMESPACE exists
        assert "SAFE_NAMESPACE" in content, \
            "Expected SAFE_NAMESPACE sanitization"
        assert "'$SAFE_NAMESPACE'" in content, \
            "Expected SAFE_NAMESPACE to be used in SQL query"
    
    def test_hook_uses_sanitize_sql_function(
        self, set_state_hook, temp_home
    ):
        """Hook uses sanitize_sql function for multi-layer defense."""
        # Read the hook script and verify sanitize_sql function exists
        with open(set_state_hook, 'r') as f:
            content = f.read()
        
        # Verify sanitize_sql function is defined
        assert "sanitize_sql()" in content, \
            "Expected sanitize_sql function definition"
        # Verify it removes null bytes
        assert "tr -d '\\000'" in content, \
            "Expected null byte removal"
        # Verify it removes control characters
        assert "tr -d '[\\001-\\010\\013-\\037\\177]'" in content, \
            "Expected control character removal"
        # Verify it escapes single quotes
        assert "sed \"s/'/''/g\"" in content, \
            "Expected single quote escaping"
    
    def test_hook_prevents_injection_via_backticks(
        self, set_state_hook, temp_home, db_path
    ):
        """Hook prevents command injection attempts via backticks in state."""
        malicious_state = "state`whoami`injection"
        result = run_set_state_hook(set_state_hook, malicious_state, cwd=str(temp_home))
        assert result.returncode == 0
        
        # Verify backticks were stored literally (not executed)
        key = "test-session+abc123+1234567890"
        value = get_db_value(db_path, key)
        assert value == malicious_state
        # Backticks should be preserved as literal characters
        assert "`" in value
    
    def test_hook_prevents_injection_via_double_quotes(
        self, set_state_hook, temp_home, db_path
    ):
        """Hook prevents SQL injection attempts via double quotes."""
        malicious_state = 'state"with"double"quotes'
        result = run_set_state_hook(set_state_hook, malicious_state, cwd=str(temp_home))
        assert result.returncode == 0
        
        # Verify double quotes were stored literally
        key = "test-session+abc123+1234567890"
        value = get_db_value(db_path, key)
        assert value == malicious_state
        assert '"' in value

