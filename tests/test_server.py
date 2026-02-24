"""Unit tests for MCP server initialization and startup."""

import json
import os
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock, call, AsyncMock

import pytest

from waggle import server
from waggle.server import (
    startup, mcp, resolve_repo_root, get_client_repo_root, cleanup_dead_sessions,
)

# Access underlying functions from decorated tools
list_agents = server.list_agents.fn
delete_repo_agents = server.delete_repo_agents.fn
close_session = server.close_session.fn
read_pane = server.read_pane.fn
send_command = server.send_command.fn
spawn_agent = server.spawn_agent.fn


# Pytest fixtures for common mock patterns
@pytest.fixture
def mock_ctx():
    """Fixture for mocked FastMCP context."""
    ctx = AsyncMock()
    ctx.list_roots = AsyncMock(return_value=[])
    return ctx


@pytest.fixture
def mock_get_sessions():
    """Fixture for mocking waggle.tmux.get_sessions in server module."""
    with patch('waggle.server.get_sessions') as mock_gs:
        yield mock_gs


@pytest.fixture
def mock_get_active_session_keys():
    """Fixture for mocking waggle.tmux.get_active_session_keys in server module."""
    with patch('waggle.server.get_active_session_keys') as mock_keys:
        yield mock_keys


@pytest.fixture
def mock_db_connection():
    """Fixture for mocking database connection with cursor."""
    with patch('waggle.server.connection') as mock_conn:
        mock_cursor = MagicMock()
        mock_conn.return_value.__enter__.return_value.cursor.return_value = mock_cursor
        mock_conn.return_value.__enter__.return_value.commit = MagicMock()
        yield mock_conn, mock_cursor


@pytest.fixture
def mock_cleanup():
    """Fixture for mocking cleanup_dead_sessions."""
    with patch('waggle.server.cleanup_dead_sessions'):
        yield


@pytest.fixture
def mock_db_path(tmp_path):
    """Fixture for mocking get_db_path to return temp path."""
    db_file = tmp_path / "test.db"
    with patch('waggle.server.get_db_path', return_value=str(db_file)):
        yield db_file


class TestServerInitialization:
    """Tests for FastMCP server instance creation."""

    def test_mcp_instance_exists(self):
        """Verify FastMCP instance is created."""
        assert mcp is not None
        assert hasattr(mcp, 'run')

    def test_mcp_server_name(self):
        """Verify server has correct name."""
        # FastMCP instance should have the correct name
        assert mcp.name == "waggle-async-agents"


class TestStartupFunction:
    """Tests for database initialization on startup."""

    def test_startup_initializes_database(self, mock_db_path):
        """Verify startup() calls init_schema with correct db_path."""
        with patch('waggle.server.init_schema') as mock_init:
            startup()
            mock_init.assert_called_once_with(str(mock_db_path))

    def test_startup_creates_database_file(self, mock_db_path):
        """Verify startup() actually creates database file."""
        startup()
        assert mock_db_path.exists()

    def test_startup_initializes_schema(self, mock_db_path):
        """Verify startup() creates state table."""
        startup()

        # Verify state table exists
        conn = sqlite3.connect(str(mock_db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='state'")
        result = cursor.fetchone()
        conn.close()

        assert result is not None
        assert result[0] == 'state'

    def test_startup_uses_config_db_path(self, tmp_path):
        """Verify startup() uses db path from get_db_path()."""
        custom_db = tmp_path / "custom" / "location.db"

        with patch('waggle.server.get_db_path', return_value=str(custom_db)):
            startup()
            assert custom_db.exists()


class TestErrorHandling:
    """Tests for error handling in server initialization."""

    def test_startup_handles_invalid_db_path(self):
        """Verify startup() handles invalid database paths."""
        # Use a path that cannot be created (e.g., invalid parent)
        invalid_path = "/nonexistent/deeply/nested/path/db.db"

        with patch('waggle.server.get_db_path', return_value=invalid_path):
            with pytest.raises(Exception):
                startup()

    def test_startup_handles_permission_error(self, tmp_path):
        """Verify startup() handles permission errors."""
        # Create read-only directory
        readonly_dir = tmp_path / "readonly"
        readonly_dir.mkdir(mode=0o444)
        db_file = readonly_dir / "test.db"

        with patch('waggle.server.get_db_path', return_value=str(db_file)):
            try:
                with pytest.raises(Exception):
                    startup()
            finally:
                # Cleanup: restore write permissions
                readonly_dir.chmod(0o755)


class TestConfigIntegration:
    """Tests for integration with config module."""

    def test_startup_respects_config_database_path(self, mock_db_path):
        """Verify startup() uses database path from config."""
        startup()
        assert mock_db_path.exists()

    def test_startup_works_without_config(self, tmp_path):
        """Verify startup() works when config returns default path."""
        default_db = tmp_path / ".waggle" / "agent_state.db"

        with patch('waggle.server.get_db_path', return_value=str(default_db)):
            startup()
            assert default_db.exists()


class TestIdempotency:
    """Tests for idempotent initialization behavior."""

    def test_startup_idempotent(self, mock_db_path):
        """Verify calling startup() multiple times is safe."""
        # Call startup multiple times
        startup()
        startup()
        startup()

        # Verify database still works
        conn = sqlite3.connect(str(mock_db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()
        conn.close()

        # Should have exactly one state table
        assert len([t for t in tables if t[0] == 'state']) == 1


class TestResolveRepoRoot:
    """Tests for resolve_repo_root helper."""

    @pytest.mark.asyncio
    async def test_resolve_repo_root_from_roots_protocol(self, mock_ctx):
        """Verify resolve_repo_root() uses roots protocol when available."""
        mock_root = MagicMock()
        mock_root.uri = "file:///path/to/repo"
        mock_ctx.list_roots = AsyncMock(return_value=[mock_root])

        result = await resolve_repo_root(mock_ctx, None)
        assert result == "/path/to/repo"

    @pytest.mark.asyncio
    async def test_resolve_repo_root_fallback_to_explicit(self, mock_ctx):
        """Verify resolve_repo_root() falls back to explicit repo_root."""
        result = await resolve_repo_root(mock_ctx, "/explicit/path")
        assert result == "/explicit/path"

    @pytest.mark.asyncio
    async def test_resolve_repo_root_raises_when_neither_available(self, mock_ctx):
        """Verify resolve_repo_root() raises error when no root available."""
        with pytest.raises(ValueError, match="does not support the roots protocol"):
            await resolve_repo_root(mock_ctx, None)

    @pytest.mark.asyncio
    async def test_resolve_repo_root_handles_percent_encoded_spaces(self, mock_ctx):
        """Verify resolve_repo_root() decodes percent-encoded spaces in file:// URIs."""
        mock_root = MagicMock()
        mock_root.uri = "file:///path/with%20spaces/repo"
        mock_ctx.list_roots = AsyncMock(return_value=[mock_root])

        result = await resolve_repo_root(mock_ctx, None)
        assert result == "/path/with spaces/repo"

    @pytest.mark.asyncio
    async def test_resolve_repo_root_handles_file_localhost_variant(self, mock_ctx):
        """Verify resolve_repo_root() handles file://localhost/ URI format."""
        mock_root = MagicMock()
        mock_root.uri = "file://localhost/path/to/repo"
        mock_ctx.list_roots = AsyncMock(return_value=[mock_root])

        result = await resolve_repo_root(mock_ctx, None)
        assert result == "/path/to/repo"

    @pytest.mark.asyncio
    async def test_resolve_repo_root_handles_localhost_with_percent_encoding(self, mock_ctx):
        """Verify resolve_repo_root() handles file://localhost/ with percent-encoded characters."""
        mock_root = MagicMock()
        mock_root.uri = "file://localhost/Users/test/my%20project/repo"
        mock_ctx.list_roots = AsyncMock(return_value=[mock_root])

        result = await resolve_repo_root(mock_ctx, None)
        assert result == "/Users/test/my project/repo"

    @pytest.mark.asyncio
    async def test_resolve_repo_root_handles_complex_percent_encoding(self, mock_ctx):
        """Verify resolve_repo_root() decodes various percent-encoded characters."""
        mock_root = MagicMock()
        # Test with spaces (%20), parentheses (%28, %29), and other special chars
        mock_root.uri = "file:///path/test%20(project)%20%5Bdev%5D"
        mock_ctx.list_roots = AsyncMock(return_value=[mock_root])

        result = await resolve_repo_root(mock_ctx, None)
        assert result == "/path/test (project) [dev]"


class TestCleanupDeadSessions:
    """Tests for cleanup_dead_sessions function."""

    def test_cleanup_dead_sessions_removes_orphaned_entries(self, mock_db_path, mock_get_active_session_keys, mock_db_connection):
        """Verify cleanup_dead_sessions removes database entries for dead tmux sessions."""
        mock_conn, mock_cursor = mock_db_connection

        # Mock active sessions — only one session is alive
        mock_get_active_session_keys.return_value = {"active-session+$0+1234567890"}

        # Database has entries for active and dead sessions
        mock_cursor.fetchall.return_value = [
            ("active-session+$0+1234567890",),
            ("dead-session+$1+1234567891",)
        ]

        cleanup_dead_sessions()

        # Verify dead session entry was deleted via batch DELETE
        delete_calls = [call for call in mock_cursor.execute.call_args_list
                       if 'DELETE' in str(call)]
        assert len(delete_calls) == 1
        # Batch DELETE uses IN clause with orphaned keys
        call_args = delete_calls[0]
        assert "DELETE FROM state WHERE key IN" in str(call_args)
        assert "dead-session+$1+1234567891" in str(call_args)

    def test_cleanup_dead_sessions_handles_no_tmux_sessions(self, mock_get_active_session_keys):
        """Verify cleanup_dead_sessions handles no tmux server gracefully."""
        # Empty set means tmux unavailable or zero sessions — early return
        mock_get_active_session_keys.return_value = set()

        # Should not raise exception and should not touch DB
        cleanup_dead_sessions()

    def test_cleanup_dead_sessions_handles_database_errors(self, mock_db_path, mock_get_active_session_keys):
        """Verify cleanup_dead_sessions silently handles database errors."""
        mock_get_active_session_keys.return_value = {"session+$0+123"}

        with patch('waggle.server.connection') as mock_conn:
            mock_conn.side_effect = Exception("Database error")

            # Should not raise exception
            cleanup_dead_sessions()

    def test_cleanup_dead_sessions_preserves_active_sessions(self, mock_db_path, mock_get_active_session_keys, mock_db_connection):
        """Verify cleanup_dead_sessions doesn't delete entries for active sessions."""
        mock_conn, mock_cursor = mock_db_connection

        mock_get_active_session_keys.return_value = {"session1+$0+111", "session2+$1+222"}

        mock_cursor.fetchall.return_value = [
            ("session1+$0+111",),
            ("session2+$1+222",)
        ]

        cleanup_dead_sessions()

        # Verify no DELETE calls for active sessions
        delete_calls = [call for call in mock_cursor.execute.call_args_list
                       if 'DELETE' in str(call)]
        assert len(delete_calls) == 0

    def test_cleanup_dead_sessions_only_removes_orphaned_entries(self, mock_db_path, mock_get_active_session_keys, mock_db_connection):
        """Verify cleanup_dead_sessions only removes dead session entries, not duplicates."""
        mock_conn, mock_cursor = mock_db_connection

        # Mock only the active session
        mock_get_active_session_keys.return_value = {"test-session+$3+1234567890"}

        # One active session and one dead session in DB
        mock_cursor.fetchall.return_value = [
            ("test-session+$3+1234567890",),  # Active
            ("dead-session+$4+9999999999",)   # Dead
        ]

        cleanup_dead_sessions()

        # Verify deletion of only the dead session
        delete_calls = [call for call in mock_cursor.execute.call_args_list
                       if 'DELETE' in str(call)]
        assert len(delete_calls) == 1
        # Verify dead session was in the orphaned keys list
        assert "dead-session+$4+9999999999" in str(delete_calls[0])


class TestListAgents:
    """Tests for list_agents MCP tool."""

    @pytest.mark.asyncio
    async def test_list_agents_returns_empty_when_no_sessions(self, mock_ctx, mock_cleanup, mock_get_sessions, mock_db_path, mock_db_connection):
        """Verify list_agents returns empty list when no DB entries exist."""
        mock_conn, mock_cursor = mock_db_connection

        # get_sessions returns empty (no tmux sessions or tmux unavailable)
        mock_get_sessions.return_value = []

        mock_cursor.fetchall.return_value = []  # No DB entries

        result = await list_agents(ctx=mock_ctx)

        assert result["status"] == "success"
        assert result["agents"] == []

    @pytest.mark.asyncio
    async def test_list_agents_excludes_sessions_without_db_entries(self, mock_ctx, mock_cleanup, mock_get_sessions, mock_db_path, mock_db_connection):
        """Verify list_agents excludes sessions without DB entries (DB as source of truth)."""
        mock_conn, mock_cursor = mock_db_connection

        # Mock get_sessions returning 2 tmux sessions
        mock_get_sessions.return_value = [
            {"session_name": "session1", "session_id": "$0", "session_created": "1234567890", "session_path": "/path1"},
            {"session_name": "session2", "session_id": "$1", "session_created": "1234567891", "session_path": "/path2"},
        ]

        mock_cursor.fetchall.return_value = []  # No db entries

        result = await list_agents(ctx=mock_ctx)

        assert result["status"] == "success"
        assert len(result["agents"]) == 0  # No agents returned because none are registered in DB

    @pytest.mark.asyncio
    async def test_list_agents_matches_status_from_database(self, tmp_path, mock_ctx, mock_cleanup, mock_get_sessions, mock_db_path, mock_db_connection):
        """Verify list_agents matches tmux sessions with database state."""
        mock_conn, mock_cursor = mock_db_connection

        mock_get_sessions.return_value = [
            {"session_name": "agent1", "session_id": "$0", "session_created": "1234567890", "session_path": "/path1"},
            {"session_name": "agent2", "session_id": "$1", "session_created": "1234567891", "session_path": "/path2"},
        ]

        mock_cursor.fetchall.return_value = [
            ("agent1+$0+1234567890", str(tmp_path), "processing data"),
            ("agent2+$1+1234567891", str(tmp_path), "awaiting user input")
        ]

        result = await list_agents(ctx=mock_ctx)

        assert result["status"] == "success"
        assert len(result["agents"]) == 2
        assert result["agents"][0]["status"] == "processing data"
        assert result["agents"][1]["status"] == "awaiting user input"

    @pytest.mark.asyncio
    async def test_list_agents_filters_by_name(self, mock_ctx, mock_cleanup, mock_get_sessions, mock_db_path, mock_db_connection):
        """Verify list_agents filters sessions by name parameter."""
        mock_conn, mock_cursor = mock_db_connection

        mock_get_sessions.return_value = [
            {"session_name": "agent1", "session_id": "$0", "session_created": "1234567890", "session_path": "/path1"},
            {"session_name": "agent2", "session_id": "$1", "session_created": "1234567891", "session_path": "/path2"},
            {"session_name": "agent3", "session_id": "$2", "session_created": "1234567892", "session_path": "/path3"},
        ]

        # Provide DB entries for all 3 agents
        mock_cursor.fetchall.return_value = [
            ("agent1+$0+1234567890", "/path1", "working"),
            ("agent2+$1+1234567891", "/path2", "waiting"),
            ("agent3+$2+1234567892", "/path3", "idle")
        ]

        result = await list_agents(name="agent2", ctx=mock_ctx)

        assert result["status"] == "success"
        assert len(result["agents"]) == 1
        assert result["agents"][0]["name"] == "agent2"

    @pytest.mark.asyncio
    async def test_list_agents_returns_error_on_database_failure(self, mock_ctx, mock_cleanup, mock_get_sessions, mock_db_path):
        """Verify list_agents returns error when database query fails."""
        mock_get_sessions.return_value = []

        with patch('waggle.server.connection') as mock_conn:
            mock_conn.side_effect = Exception("Database unreachable")

            result = await list_agents(ctx=mock_ctx)

        assert result["status"] == "error"
        assert "Failed to query database" in result["error"]

    @pytest.mark.asyncio
    async def test_list_agents_handles_tmux_not_installed(self, mock_ctx, mock_cleanup, mock_get_sessions, mock_db_path, mock_db_connection):
        """Verify list_agents returns DB agents even when tmux is not installed."""
        mock_conn, mock_cursor = mock_db_connection
        # get_sessions handles errors internally and returns []
        mock_get_sessions.return_value = []

        # DB has one registered agent
        mock_cursor.fetchall.return_value = [
            ("agent1+$0+1234567890", "/path1", "working")
        ]

        result = await list_agents(ctx=mock_ctx)

        assert result["status"] == "success"
        assert len(result["agents"]) == 1
        assert result["agents"][0]["name"] == "agent1"
        assert result["agents"][0]["directory"] is None  # Couldn't enrich with tmux data

    @pytest.mark.asyncio
    async def test_list_agents_includes_namespace_field(self, mock_ctx, mock_cleanup, mock_get_sessions, mock_db_path, mock_db_connection):
        """Verify list_agents includes namespace field in output."""
        mock_conn, mock_cursor = mock_db_connection

        mock_get_sessions.return_value = [
            {"session_name": "agent1", "session_id": "$0", "session_created": "1234567890", "session_path": "/path1"},
            {"session_name": "agent2", "session_id": "$1", "session_created": "1234567891", "session_path": "/path2"},
        ]

        mock_cursor.fetchall.return_value = [
            ("agent1+$0+1234567890", "/repo/waggle", "working"),
            ("agent2+$1+1234567891", "/repo/other", "waiting")
        ]

        result = await list_agents(ctx=mock_ctx)

        assert result["status"] == "success"
        assert len(result["agents"]) == 2
        assert result["agents"][0]["repo"] == "/repo/waggle"
        assert result["agents"][1]["repo"] == "/repo/other"

    @pytest.mark.asyncio
    async def test_list_agents_namespace_none_when_no_state(self, mock_ctx, mock_cleanup, mock_get_sessions, mock_db_path, mock_db_connection):
        """Verify list_agents returns empty when no database entries (DB as source of truth)."""
        mock_conn, mock_cursor = mock_db_connection

        mock_get_sessions.return_value = [
            {"session_name": "agent1", "session_id": "$0", "session_created": "1234567890", "session_path": "/path1"},
        ]

        mock_cursor.fetchall.return_value = []  # No db entries

        result = await list_agents(ctx=mock_ctx)

        assert result["status"] == "success"
        assert len(result["agents"]) == 0  # No agents because none registered in DB

    @pytest.mark.asyncio
    async def test_list_agents_filters_by_repo(self, mock_ctx, mock_cleanup, mock_get_sessions, mock_db_path, mock_db_connection):
        """Verify list_agents filters by repo parameter (case-insensitive)."""
        mock_conn, mock_cursor = mock_db_connection

        mock_get_sessions.return_value = [
            {"session_name": "agent1", "session_id": "$0", "session_created": "1234567890", "session_path": "/path1"},
            {"session_name": "agent2", "session_id": "$1", "session_created": "1234567891", "session_path": "/path2"},
            {"session_name": "agent3", "session_id": "$2", "session_created": "1234567892", "session_path": "/path3"},
        ]

        mock_cursor.fetchall.return_value = [
            ("agent1+$0+1234567890", "/projects/waggle", "working"),
            ("agent2+$1+1234567891", "/projects/other", "waiting"),
            ("agent3+$2+1234567892", "/home/Waggle", "idle")
        ]

        result = await list_agents(repo="waggle", ctx=mock_ctx)

        assert result["status"] == "success"
        assert len(result["agents"]) == 2
        assert result["agents"][0]["name"] == "agent1"
        assert result["agents"][0]["repo"] == "/projects/waggle"
        assert result["agents"][1]["name"] == "agent3"
        assert result["agents"][1]["repo"] == "/home/Waggle"

    @pytest.mark.asyncio
    async def test_list_agents_filters_by_repo_case_insensitive(self, mock_ctx, mock_cleanup, mock_get_sessions, mock_db_path, mock_db_connection):
        """Verify list_agents repo filter is case-insensitive."""
        mock_conn, mock_cursor = mock_db_connection

        mock_get_sessions.return_value = [
            {"session_name": "agent1", "session_id": "$0", "session_created": "1234567890", "session_path": "/path1"},
            {"session_name": "agent2", "session_id": "$1", "session_created": "1234567891", "session_path": "/path2"},
        ]

        mock_cursor.fetchall.return_value = [
            ("agent1+$0+1234567890", "/Projects/WAGGLE", "working"),
            ("agent2+$1+1234567891", "/projects/other", "waiting")
        ]

        result = await list_agents(repo="waggle", ctx=mock_ctx)

        assert result["status"] == "success"
        assert len(result["agents"]) == 1
        assert result["agents"][0]["name"] == "agent1"

    @pytest.mark.asyncio
    async def test_list_agents_repo_filter_excludes_none_namespace(self, mock_ctx, mock_cleanup, mock_get_sessions, mock_db_path, mock_db_connection):
        """Verify list_agents repo filter excludes sessions with None namespace."""
        mock_conn, mock_cursor = mock_db_connection

        mock_get_sessions.return_value = [
            {"session_name": "agent1", "session_id": "$0", "session_created": "1234567890", "session_path": "/path1"},
            {"session_name": "agent2", "session_id": "$1", "session_created": "1234567891", "session_path": "/path2"},
        ]

        # Only one agent has state, other will have None repo
        mock_cursor.fetchall.return_value = [
            ("agent1+$0+1234567890", "/projects/waggle", "working")
        ]

        result = await list_agents(repo="waggle", ctx=mock_ctx)

        assert result["status"] == "success"
        assert len(result["agents"]) == 1
        assert result["agents"][0]["name"] == "agent1"

    @pytest.mark.asyncio
    async def test_list_agents_without_repo_filter_returns_all(self, mock_ctx, mock_cleanup, mock_get_sessions, mock_db_path, mock_db_connection):
        """Verify list_agents without repo parameter returns all DB-registered agents."""
        mock_conn, mock_cursor = mock_db_connection

        mock_get_sessions.return_value = [
            {"session_name": "agent1", "session_id": "$0", "session_created": "1234567890", "session_path": "/path1"},
            {"session_name": "agent2", "session_id": "$1", "session_created": "1234567891", "session_path": "/path2"},
            {"session_name": "agent3", "session_id": "$2", "session_created": "1234567892", "session_path": "/path3"},
        ]

        mock_cursor.fetchall.return_value = [
            ("agent1+$0+1234567890", "/projects/waggle", "working"),
            ("agent2+$1+1234567891", "/projects/other", "waiting")
        ]

        result = await list_agents(ctx=mock_ctx)

        assert result["status"] == "success"
        assert len(result["agents"]) == 2  # Only DB-registered agents returned
        assert result["agents"][0]["name"] == "agent1"
        assert result["agents"][1]["name"] == "agent2"

    @pytest.mark.asyncio
    async def test_list_agents_excludes_unregistered_tmux_sessions(self, mock_ctx, mock_cleanup, mock_get_sessions, mock_db_path, mock_db_connection):
        """Verify sessions without DB entries are excluded from list_agents output."""
        mock_conn, mock_cursor = mock_db_connection

        # Mock get_sessions with 3 tmux sessions
        mock_get_sessions.return_value = [
            {"session_name": "registered-agent", "session_id": "$0", "session_created": "1234567890", "session_path": "/projects/waggle"},
            {"session_name": "unregistered-session", "session_id": "$1", "session_created": "1234567891", "session_path": "/random/path"},
            {"session_name": "another-unregistered", "session_id": "$2", "session_created": "1234567892", "session_path": "/other/path"},
        ]

        # Only one session registered in DB
        mock_cursor.fetchall.return_value = [
            ("registered-agent+$0+1234567890", "/projects/waggle", "working")
        ]

        result = await list_agents(ctx=mock_ctx)

        assert result["status"] == "success"
        assert len(result["agents"]) == 1  # Only registered agent returned
        assert result["agents"][0]["name"] == "registered-agent"
        assert result["agents"][0]["status"] == "working"
        # Unregistered sessions are completely excluded


class TestDeleteRepoAgents:
    """Tests for delete_repo_agents MCP tool."""

    @pytest.mark.asyncio
    async def test_cleanup_deletes_namespace_entries(self, tmp_path, mock_ctx, mock_db_path, mock_db_connection):
        """Verify delete_repo_agents deletes all entries for namespace."""
        mock_conn, mock_cursor = mock_db_connection
        mock_cursor.rowcount = 3  # 3 entries deleted

        result = await delete_repo_agents(repo_root=str(tmp_path), ctx=mock_ctx)

        assert result["status"] == "success"
        assert result["deleted_count"] == 3

    @pytest.mark.asyncio
    async def test_cleanup_respects_namespace_isolation(self, tmp_path, mock_ctx, mock_db_path, mock_db_connection):
        """Verify delete_repo_agents only deletes entries for specified namespace."""
        mock_conn, mock_cursor = mock_db_connection
        mock_cursor.rowcount = 2

        await delete_repo_agents(repo_root=str(tmp_path), ctx=mock_ctx)

        # Verify DELETE query uses repo column filter with subdirectory matching
        calls = mock_cursor.execute.call_args_list
        delete_call = calls[0]  # Now only one call (DELETE)
        assert delete_call[0][0] == "DELETE FROM state WHERE repo = ? OR repo LIKE ?"
        assert delete_call[0][1] == (str(tmp_path), f"{str(tmp_path)}/%")

    @pytest.mark.asyncio
    async def test_cleanup_returns_zero_when_no_entries(self, tmp_path, mock_ctx, mock_db_path, mock_db_connection):
        """Verify delete_repo_agents returns 0 when no entries to delete."""
        mock_conn, mock_cursor = mock_db_connection
        mock_cursor.rowcount = 0  # No entries deleted

        result = await delete_repo_agents(repo_root=str(tmp_path), ctx=mock_ctx)

        assert result["status"] == "success"
        assert result["deleted_count"] == 0

    @pytest.mark.asyncio
    async def test_cleanup_returns_error_on_database_failure(self, tmp_path, mock_ctx, mock_db_path):
        """Verify delete_repo_agents returns error when database operation fails."""
        with patch('waggle.server.connection') as mock_conn:
            mock_conn.side_effect = Exception("Database connection failed")

            result = await delete_repo_agents(repo_root=str(tmp_path), ctx=mock_ctx)

        assert result["status"] == "error"
        assert "Failed to clean up database" in result["error"]

    @pytest.mark.asyncio
    async def test_cleanup_does_not_affect_other_namespaces(self, tmp_path, mock_ctx, mock_db_path, mock_db_connection):
        """Verify delete_repo_agents doesn't delete entries from other namespaces."""
        mock_conn, mock_cursor = mock_db_connection
        namespace1 = str(tmp_path / "repo1")
        mock_cursor.rowcount = 2  # 2 entries deleted in this namespace

        result = await delete_repo_agents(repo_root=namespace1, ctx=mock_ctx)

        # Verify DELETE query uses specific namespace with subdirectory matching
        calls = mock_cursor.execute.call_args_list
        delete_call = calls[0]  # Only call is DELETE
        assert delete_call[0][1] == (namespace1, f"{namespace1}/%")

    @pytest.mark.asyncio
    async def test_cleanup_deletes_subdirectory_agents(self, tmp_path):
        """Verify delete_repo_agents deletes agents in subdirectories."""
        mock_ctx = AsyncMock()
        mock_ctx.list_roots = AsyncMock(return_value=[])
        db_file = tmp_path / "test.db"

        with patch('waggle.server.get_db_path', return_value=str(db_file)):
            # Initialize real database
            from waggle.database import init_schema
            init_schema(str(db_file))

            # Insert test data: agents in repo root, subdirectory, and unrelated path
            repo_root = "/Users/test/myrepo"
            conn = sqlite3.connect(str(db_file))
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO state (key, repo, status) VALUES (?, ?, ?)",
                ("agent1+$0+111", repo_root, "working")
            )
            cursor.execute(
                "INSERT INTO state (key, repo, status) VALUES (?, ?, ?)",
                ("agent2+$0+222", f"{repo_root}/src", "working")
            )
            cursor.execute(
                "INSERT INTO state (key, repo, status) VALUES (?, ?, ?)",
                ("agent3+$0+333", f"{repo_root}/tests/unit", "working")
            )
            cursor.execute(
                "INSERT INTO state (key, repo, status) VALUES (?, ?, ?)",
                ("agent4+$0+444", "/Users/test/other-repo", "working")
            )
            conn.commit()
            conn.close()

            # Delete agents for repo_root
            result = await delete_repo_agents(
                repo_root=repo_root,
                ctx=mock_ctx
            )

            # Verify result
            assert result["status"] == "success"
            assert result["deleted_count"] == 3  # agent1, agent2, agent3 deleted

            # Verify database state
            conn = sqlite3.connect(str(db_file))
            cursor = conn.cursor()
            cursor.execute("SELECT key FROM state")
            remaining = cursor.fetchall()
            conn.close()

            # Only agent4 should remain
            assert len(remaining) == 1
            assert remaining[0][0] == "agent4+$0+444"

    @pytest.mark.asyncio
    async def test_cleanup_does_not_delete_similar_paths(self, tmp_path):
        """Verify delete_repo_agents doesn't delete agents with similar but different paths."""
        mock_ctx = AsyncMock()
        mock_ctx.list_roots = AsyncMock(return_value=[])
        db_file = tmp_path / "test.db"

        with patch('waggle.server.get_db_path', return_value=str(db_file)):
            # Initialize real database
            from waggle.database import init_schema
            init_schema(str(db_file))

            # Insert test data: similar paths that should NOT be deleted
            target_repo = "/Users/test/waggle"
            conn = sqlite3.connect(str(db_file))
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO state (key, repo, status) VALUES (?, ?, ?)",
                ("agent1+$0+111", target_repo, "working")
            )
            cursor.execute(
                "INSERT INTO state (key, repo, status) VALUES (?, ?, ?)",
                ("agent2+$0+222", "/Users/test/waggle-dev", "working")
            )
            cursor.execute(
                "INSERT INTO state (key, repo, status) VALUES (?, ?, ?)",
                ("agent3+$0+333", "/Users/test/waggle2", "working")
            )
            cursor.execute(
                "INSERT INTO state (key, repo, status) VALUES (?, ?, ?)",
                ("agent4+$0+444", "/Users/other/waggle", "working")
            )
            conn.commit()
            conn.close()

            # Delete agents for target_repo only
            result = await delete_repo_agents(
                repo_root=target_repo,
                ctx=mock_ctx
            )

            # Verify result
            assert result["status"] == "success"
            assert result["deleted_count"] == 1  # Only agent1 deleted

            # Verify database state
            conn = sqlite3.connect(str(db_file))
            cursor = conn.cursor()
            cursor.execute("SELECT key FROM state ORDER BY key")
            remaining = cursor.fetchall()
            conn.close()

            # agent2, agent3, agent4 should remain
            assert len(remaining) == 3
            assert remaining[0][0] == "agent2+$0+222"
            assert remaining[1][0] == "agent3+$0+333"
            assert remaining[2][0] == "agent4+$0+444"

    @pytest.mark.asyncio
    async def test_cleanup_handles_trailing_slash(self, tmp_path):
        """Verify delete_repo_agents normalizes paths with trailing slashes correctly."""
        mock_ctx = AsyncMock()
        mock_ctx.list_roots = AsyncMock(return_value=[])
        db_file = tmp_path / "test.db"

        with patch('waggle.server.get_db_path', return_value=str(db_file)):
            # Initialize real database
            from waggle.database import init_schema
            init_schema(str(db_file))

            # Insert test data
            repo_root = "/Users/test/myrepo"
            conn = sqlite3.connect(str(db_file))
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO state (key, repo, status) VALUES (?, ?, ?)",
                ("agent1+$0+111", repo_root, "working")
            )
            cursor.execute(
                "INSERT INTO state (key, repo, status) VALUES (?, ?, ?)",
                ("agent2+$0+222", f"{repo_root}/src", "working")
            )
            conn.commit()
            conn.close()

            # Delete with trailing slash - should be normalized to match
            result = await delete_repo_agents(
                repo_root=f"{repo_root}/",  # Note trailing slash
                ctx=mock_ctx
            )

            # Verify: trailing slash is normalized, so deletion succeeds
            # normalize_path() removes trailing slashes before matching
            assert result["status"] == "success"
            assert result["deleted_count"] == 2  # Both agents deleted after normalization

            # Verify database state - no agents remain
            conn = sqlite3.connect(str(db_file))
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM state")
            count = cursor.fetchone()[0]
            conn.close()

            assert count == 0


class TestListAgentsCustomStates:
    """Tests for custom state values in list_agents."""

    @pytest.mark.asyncio
    async def test_list_agents_shows_custom_state_session_started(self, tmp_path, mock_ctx, mock_cleanup, mock_get_sessions, mock_db_path, mock_db_connection):
        """Verify list_agents displays custom state 'session started'."""
        mock_conn, mock_cursor = mock_db_connection

        mock_get_sessions.return_value = [
            {"session_name": "test-agent", "session_id": "$0", "session_created": "1234567890", "session_path": "/path1"},
        ]

        mock_cursor.fetchall.return_value = [
            ("test-agent+$0+1234567890", str(tmp_path), "session started")
        ]

        result = await list_agents(ctx=mock_ctx)

        assert result["status"] == "success"
        assert len(result["agents"]) == 1
        assert result["agents"][0]["status"] == "session started"

    @pytest.mark.asyncio
    async def test_list_agents_shows_custom_state_need_permission(self, tmp_path, mock_ctx, mock_cleanup, mock_get_sessions, mock_db_path, mock_db_connection):
        """Verify list_agents displays custom state 'need permission'."""
        mock_conn, mock_cursor = mock_db_connection

        mock_get_sessions.return_value = [
            {"session_name": "agent2", "session_id": "$0", "session_created": "1234567890", "session_path": "/path1"},
        ]

        mock_cursor.fetchall.return_value = [
            ("agent2+$0+1234567890", str(tmp_path), "need permission")
        ]

        result = await list_agents(ctx=mock_ctx)

        assert result["status"] == "success"
        assert len(result["agents"]) == 1
        assert result["agents"][0]["status"] == "need permission"

    @pytest.mark.asyncio
    async def test_list_agents_shows_custom_state_processing_data(self, tmp_path, mock_ctx, mock_cleanup, mock_get_sessions, mock_db_path, mock_db_connection):
        """Verify list_agents displays custom state 'processing data'."""
        mock_conn, mock_cursor = mock_db_connection

        mock_get_sessions.return_value = [
            {"session_name": "worker", "session_id": "$0", "session_created": "1234567890", "session_path": "/path1"},
        ]

        mock_cursor.fetchall.return_value = [
            ("worker+$0+1234567890", str(tmp_path), "processing data")
        ]

        result = await list_agents(ctx=mock_ctx)

        assert result["status"] == "success"
        assert len(result["agents"]) == 1
        assert result["agents"][0]["status"] == "processing data"

    @pytest.mark.asyncio
    async def test_list_agents_multiple_agents_different_custom_states(self, tmp_path, mock_ctx, mock_cleanup, mock_get_sessions, mock_db_path, mock_db_connection):
        """Verify list_agents correctly displays multiple agents with different custom states."""
        mock_conn, mock_cursor = mock_db_connection

        mock_get_sessions.return_value = [
            {"session_name": "agent1", "session_id": "$0", "session_created": "1111111111", "session_path": "/path1"},
            {"session_name": "agent2", "session_id": "$1", "session_created": "2222222222", "session_path": "/path2"},
            {"session_name": "agent3", "session_id": "$2", "session_created": "3333333333", "session_path": "/path3"},
        ]

        mock_cursor.fetchall.return_value = [
            ("agent1+$0+1111111111", str(tmp_path), "session started"),
            ("agent2+$1+2222222222", str(tmp_path), "need permission"),
            ("agent3+$2+3333333333", str(tmp_path), "processing data")
        ]

        result = await list_agents(ctx=mock_ctx)

        assert result["status"] == "success"
        assert len(result["agents"]) == 3
        assert result["agents"][0]["name"] == "agent1"
        assert result["agents"][0]["status"] == "session started"
        assert result["agents"][1]["name"] == "agent2"
        assert result["agents"][1]["status"] == "need permission"
        assert result["agents"][2]["name"] == "agent3"
        assert result["agents"][2]["status"] == "processing data"

    @pytest.mark.asyncio
    async def test_list_agents_custom_states_with_unknown_status(self, tmp_path, mock_ctx, mock_cleanup, mock_get_sessions, mock_db_path, mock_db_connection):
        """Verify list_agents shows only DB-registered agents with custom states."""
        mock_conn, mock_cursor = mock_db_connection

        # Return 4 sessions from get_sessions
        mock_get_sessions.return_value = [
            {"session_name": "with-state1", "session_id": "$0", "session_created": "1111111111", "session_path": "/path1"},
            {"session_name": "no-state", "session_id": "$1", "session_created": "2222222222", "session_path": "/path2"},
            {"session_name": "with-state2", "session_id": "$2", "session_created": "3333333333", "session_path": "/path3"},
            {"session_name": "no-state2", "session_id": "$3", "session_created": "4444444444", "session_path": "/path4"},
        ]

        # Only return db entries for 2 agents
        mock_cursor.fetchall.return_value = [
            ("with-state1+$0+1111111111", str(tmp_path), "session started"),
            ("with-state2+$2+3333333333", str(tmp_path), "processing data")
        ]

        result = await list_agents(ctx=mock_ctx)

        assert result["status"] == "success"
        assert len(result["agents"]) == 2  # Only DB-registered agents returned
        # Agents with custom states
        assert result["agents"][0]["name"] == "with-state1"
        assert result["agents"][0]["status"] == "session started"
        assert result["agents"][1]["name"] == "with-state2"
        assert result["agents"][1]["status"] == "processing data"
        # Agents without db entries are excluded entirely


class TestListAgentsCleanupIntegration:
    """Integration tests verifying cleanup runs before list_agents returns."""

    @pytest.mark.asyncio
    async def test_list_agents_removes_dead_sessions_before_returning(self, tmp_path):
        """Verify cleanup_dead_sessions runs and removes stale entries before list_agents returns results."""
        mock_ctx = AsyncMock()
        mock_ctx.list_roots = AsyncMock(return_value=[])

        db_path = tmp_path / "test.db"
        namespace = str(tmp_path)

        # Create database with entries for both live and dead sessions
        conn = sqlite3.connect(str(db_path))
        conn.execute("""
            CREATE TABLE IF NOT EXISTS state (
                key TEXT PRIMARY KEY,
                repo TEXT NOT NULL,
                status TEXT NOT NULL,
                updated_at TIMESTAMP
            )
        """)
        # Live session (will be returned by tmux)
        conn.execute(
            "INSERT INTO state (key, repo, status) VALUES (?, ?, ?)",
            ("live-agent+$0+1234567890", namespace, "analyzing code")
        )
        # Dead session (will NOT be returned by tmux - should be cleaned up)
        conn.execute(
            "INSERT INTO state (key, repo, status) VALUES (?, ?, ?)",
            ("dead-agent+$1+1234567891", namespace, "waiting for permission")
        )
        conn.commit()
        conn.close()

        # Mock get_active_session_keys for cleanup_dead_sessions
        mock_active_keys = {"live-agent+$0+1234567890"}

        # Mock get_sessions for list_agents enrichment
        mock_sessions = [
            {"session_name": "live-agent", "session_id": "$0", "session_created": "1234567890", "session_path": namespace},
        ]

        with patch('waggle.server.get_active_session_keys', return_value=mock_active_keys):
            with patch('waggle.server.get_sessions', return_value=mock_sessions):
                with patch('waggle.server.get_db_path', return_value=str(db_path)):
                    # Call list_agents WITHOUT mocking cleanup_dead_sessions
                    # This tests that cleanup actually runs
                    result = await list_agents(
                        ctx=mock_ctx
                    )

        # Verify only live session is returned
        assert result["status"] == "success"
        assert len(result["agents"]) == 1
        assert result["agents"][0]["name"] == "live-agent"
        assert result["agents"][0]["status"] == "analyzing code"

        # Verify dead session was removed from database
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT key FROM state")
        remaining_keys = [row[0] for row in cursor.fetchall()]
        conn.close()

        # Only live session should remain
        assert len(remaining_keys) == 1
        assert remaining_keys[0] == "live-agent+$0+1234567890"


class TestCustomStateEndToEnd:
    """End-to-end integration tests for custom state workflow."""


    @pytest.mark.asyncio
    async def test_custom_state_persistence_across_multiple_list_calls(self, tmp_path):
        """Verify custom state persists across multiple list_agents calls."""
        mock_ctx = AsyncMock()
        mock_ctx.list_roots = AsyncMock(return_value=[])

        db_path = tmp_path / "test.db"
        namespace = str(tmp_path)

        # Initialize database with custom state
        conn = sqlite3.connect(str(db_path))
        conn.execute("""
            CREATE TABLE IF NOT EXISTS state (
                key TEXT PRIMARY KEY,
                repo TEXT NOT NULL,
                status TEXT NOT NULL,
                updated_at TIMESTAMP
            )
        """)
        conn.execute(
            "INSERT INTO state (key, repo, status) VALUES (?, ?, ?)",
            ("persistent-agent+$0+1234567890", namespace, "processing data")
        )
        conn.commit()
        conn.close()

        # Mock get_active_session_keys for cleanup_dead_sessions
        mock_active_keys = {"persistent-agent+$0+1234567890"}

        # Mock get_sessions for list_agents enrichment
        mock_sessions = [
            {"session_name": "persistent-agent", "session_id": "$0", "session_created": "1234567890", "session_path": namespace},
        ]

        # Call list_agents multiple times
        for i in range(3):
            with patch('waggle.server.get_active_session_keys', return_value=mock_active_keys):
                with patch('waggle.server.get_sessions', return_value=mock_sessions):
                    with patch('waggle.server.get_db_path', return_value=str(db_path)):
                        result = await list_agents(
                            ctx=mock_ctx
                        )

            # Verify state is consistent across all calls
            assert result["status"] == "success"
            assert len(result["agents"]) == 1
            assert result["agents"][0]["name"] == "persistent-agent"


class TestCloseSession:
    """Tests for close_session() — terminates a waggle-managed tmux session."""

    def _make_db_with_session(self, db_path: str, session_id: str, session_name: str) -> str:
        """Insert a state row using the real schema (key, repo, status, updated_at)."""
        key = f"{session_name}+{session_id}+1111111111"
        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO state (key, repo, status, updated_at) VALUES (?, ?, ?, ?)",
            (key, "/repo", "idle", "2024-01-01T00:00:00"),
        )
        conn.commit()
        conn.close()
        return key

    @pytest.mark.asyncio
    async def test_session_not_in_db_returns_error(self, mock_db_path):
        """Verify error when session_id has no DB entry."""
        from waggle.database import init_schema
        init_schema(str(mock_db_path))

        result = await close_session("$99")

        assert result["status"] == "error"
        assert "$99" in result["message"]

    @pytest.mark.asyncio
    async def test_session_name_mismatch_returns_error(self, mock_db_path):
        """Verify error when session_name doesn't match DB/tmux session."""
        from waggle.database import init_schema
        init_schema(str(mock_db_path))
        self._make_db_with_session(str(mock_db_path), "$1", "agent1")

        with patch("waggle.server.validate_session_name_id", new_callable=AsyncMock) as mock_validate:
            mock_validate.return_value = {"status": "error", "message": "Session name mismatch"}

            result = await close_session("$1", session_name="wrong-name")

        assert result["status"] == "error"
        assert "mismatch" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_llm_running_without_force_returns_error(self, mock_db_path):
        """Verify error when LLM is running and force=False with exact message."""
        from waggle.database import init_schema
        init_schema(str(mock_db_path))
        self._make_db_with_session(str(mock_db_path), "$1", "agent1")

        with patch("waggle.server.check_llm_running", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = True

            result = await close_session("$1")

        assert result["status"] == "error"
        assert result["message"] == "Active LLM agent, call again with force=true to confirm"

    @pytest.mark.asyncio
    async def test_llm_running_with_force_proceeds(self, mock_db_path):
        """Verify close proceeds when LLM is running and force=True."""
        from waggle.database import init_schema
        init_schema(str(mock_db_path))
        self._make_db_with_session(str(mock_db_path), "$1", "agent1")

        with patch("waggle.server.check_llm_running", new_callable=AsyncMock) as mock_llm, \
             patch("waggle.server.kill_session", new_callable=AsyncMock) as mock_kill:
            mock_llm.return_value = True
            mock_kill.return_value = {"status": "success"}

            result = await close_session("$1", force=True)

        assert result["status"] == "success"
        mock_kill.assert_called_once_with("$1")

    @pytest.mark.asyncio
    async def test_no_llm_proceeds_without_force(self, mock_db_path):
        """Verify close proceeds when no LLM is running, without force."""
        from waggle.database import init_schema
        init_schema(str(mock_db_path))
        self._make_db_with_session(str(mock_db_path), "$1", "agent1")

        with patch("waggle.server.check_llm_running", new_callable=AsyncMock) as mock_llm, \
             patch("waggle.server.kill_session", new_callable=AsyncMock) as mock_kill:
            mock_llm.return_value = False
            mock_kill.return_value = {"status": "success"}

            result = await close_session("$1")

        assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_kill_failure_after_db_delete_returns_partial_error(self, mock_db_path):
        """Verify error with DB-removed message when tmux kill fails after DB delete."""
        from waggle.database import init_schema
        init_schema(str(mock_db_path))
        self._make_db_with_session(str(mock_db_path), "$1", "agent1")

        with patch("waggle.server.check_llm_running", new_callable=AsyncMock) as mock_llm, \
             patch("waggle.server.kill_session", new_callable=AsyncMock) as mock_kill:
            mock_llm.return_value = False
            mock_kill.return_value = {"status": "error", "message": "tmux error"}

            result = await close_session("$1")

        assert result["status"] == "error"
        assert "DB entry removed" in result["message"]
        assert "tmux error" in result["message"]

    @pytest.mark.asyncio
    async def test_db_entry_removed_on_success(self, mock_db_path):
        """Verify DB entry is deleted after successful close."""
        import sqlite3
        from waggle.database import init_schema
        init_schema(str(mock_db_path))
        self._make_db_with_session(str(mock_db_path), "$1", "agent1")

        with patch("waggle.server.check_llm_running", new_callable=AsyncMock) as mock_llm, \
             patch("waggle.server.kill_session", new_callable=AsyncMock) as mock_kill:
            mock_llm.return_value = False
            mock_kill.return_value = {"status": "success"}

            await close_session("$1")

        conn = sqlite3.connect(str(mock_db_path))
        rows = conn.execute("SELECT key FROM state WHERE key LIKE '%$1%'").fetchall()
        conn.close()
        assert rows == []

    @pytest.mark.asyncio
    async def test_success_returns_correct_message(self, mock_db_path):
        """Verify success response has expected status and message."""
        from waggle.database import init_schema
        init_schema(str(mock_db_path))
        self._make_db_with_session(str(mock_db_path), "$1", "agent1")

        with patch("waggle.server.check_llm_running", new_callable=AsyncMock) as mock_llm, \
             patch("waggle.server.kill_session", new_callable=AsyncMock) as mock_kill:
            mock_llm.return_value = False
            mock_kill.return_value = {"status": "success"}

            result = await close_session("$1")

        assert result == {"status": "success", "message": "Session closed"}

    @pytest.mark.asyncio
    async def test_db_delete_precedes_tmux_kill(self, mock_db_path):
        """Verify DB entry is already gone when kill_session is called (DB-first ordering)."""
        import sqlite3
        from waggle.database import init_schema
        init_schema(str(mock_db_path))
        self._make_db_with_session(str(mock_db_path), "$1", "agent1")

        db_was_empty_at_kill = []

        async def check_db_then_succeed(session_id):
            """Side-effect that checks DB state when kill_session is called."""
            conn = sqlite3.connect(str(mock_db_path))
            rows = conn.execute(
                "SELECT key FROM state WHERE key LIKE ?", (f"%+{session_id}+%",)
            ).fetchall()
            conn.close()
            db_was_empty_at_kill.append(len(rows) == 0)
            return {"status": "success"}

        with patch("waggle.server.check_llm_running", new_callable=AsyncMock, return_value=False), \
             patch("waggle.server.kill_session", side_effect=check_db_then_succeed):

            result = await close_session("$1")

        assert result["status"] == "success"
        assert db_was_empty_at_kill == [True], "DB entry must be deleted before tmux kill"


class TestReadPane:
    """Tests for read_pane() MCP tool — pane capture and state detection."""

    def _insert_session(self, db_path: str, session_id: str, session_name: str) -> str:
        """Insert a state row and return the key."""
        key = f"{session_name}+{session_id}+1111111111"
        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO state (key, repo, status, updated_at) VALUES (?, ?, ?, ?)",
            (key, "/repo", "working", "2024-01-01T00:00:00"),
        )
        conn.commit()
        conn.close()
        return key

    @pytest.mark.asyncio
    async def test_unregistered_session_returns_error(self, mock_db_path):
        """Verify error when session_id has no DB entry."""
        from waggle.database import init_schema
        init_schema(str(mock_db_path))

        result = await read_pane("$99")

        assert result["status"] == "error"
        assert "$99" in result["message"]

    @pytest.mark.asyncio
    async def test_returns_working_state(self, mock_db_path):
        """Verify correct agent_state and None prompt_data for working state."""
        from waggle.database import init_schema
        init_schema(str(mock_db_path))
        self._insert_session(str(mock_db_path), "$1", "agent1")

        with patch("waggle.server.capture_pane", new_callable=AsyncMock) as mock_capture, \
             patch("waggle.server.state_parser.parse") as mock_parse:
            mock_capture.return_value = {"status": "success", "content": "Esc to interrupt"}
            mock_parse.return_value = ("working", None)

            result = await read_pane("$1")

        assert result["status"] == "success"
        assert result["agent_state"] == "working"
        assert result["content"] == "Esc to interrupt"
        assert result["prompt_data"] is None

    @pytest.mark.asyncio
    async def test_returns_done_state(self, mock_db_path):
        """Verify correct agent_state and None prompt_data for done state."""
        from waggle.database import init_schema
        init_schema(str(mock_db_path))
        self._insert_session(str(mock_db_path), "$1", "agent1")

        with patch("waggle.server.capture_pane", new_callable=AsyncMock) as mock_capture, \
             patch("waggle.server.state_parser.parse") as mock_parse:
            mock_capture.return_value = {"status": "success", "content": ">\n"}
            mock_parse.return_value = ("done", None)

            result = await read_pane("$1")

        assert result["status"] == "success"
        assert result["agent_state"] == "done"
        assert result["prompt_data"] is None

    @pytest.mark.asyncio
    async def test_returns_ask_user_state_with_prompt_data(self, mock_db_path):
        """Verify correct agent_state and populated prompt_data for ask_user state."""
        from waggle.database import init_schema
        init_schema(str(mock_db_path))
        self._insert_session(str(mock_db_path), "$1", "agent1")

        expected_prompt_data = {"question": "Pick one", "options": [{"number": 1, "label": "Yes", "description": ""}]}

        with patch("waggle.server.capture_pane", new_callable=AsyncMock) as mock_capture, \
             patch("waggle.server.state_parser.parse") as mock_parse:
            mock_capture.return_value = {"status": "success", "content": "Pick one\n❯ ───\n❯ 1. Yes"}
            mock_parse.return_value = ("ask_user", expected_prompt_data)

            result = await read_pane("$1")

        assert result["status"] == "success"
        assert result["agent_state"] == "ask_user"
        assert result["prompt_data"] == expected_prompt_data

    @pytest.mark.asyncio
    async def test_returns_check_permission_state_with_prompt_data(self, mock_db_path):
        """Verify correct agent_state and populated prompt_data for check_permission state."""
        from waggle.database import init_schema
        init_schema(str(mock_db_path))
        self._insert_session(str(mock_db_path), "$1", "agent1")

        expected_prompt_data = {"tool_type": "Bash", "command": "rm -rf /tmp", "description": ""}

        with patch("waggle.server.capture_pane", new_callable=AsyncMock) as mock_capture, \
             patch("waggle.server.state_parser.parse") as mock_parse:
            mock_capture.return_value = {"status": "success", "content": "Permission rule\nDo you want to proceed?"}
            mock_parse.return_value = ("check_permission", expected_prompt_data)

            result = await read_pane("$1")

        assert result["status"] == "success"
        assert result["agent_state"] == "check_permission"
        assert result["prompt_data"] == expected_prompt_data

    @pytest.mark.asyncio
    async def test_returns_unknown_state(self, mock_db_path):
        """Verify correct agent_state and None prompt_data for unknown state."""
        from waggle.database import init_schema
        init_schema(str(mock_db_path))
        self._insert_session(str(mock_db_path), "$1", "agent1")

        with patch("waggle.server.capture_pane", new_callable=AsyncMock) as mock_capture, \
             patch("waggle.server.state_parser.parse") as mock_parse:
            mock_capture.return_value = {"status": "success", "content": "random output"}
            mock_parse.return_value = ("unknown", None)

            result = await read_pane("$1")

        assert result["status"] == "success"
        assert result["agent_state"] == "unknown"
        assert result["prompt_data"] is None

    @pytest.mark.asyncio
    async def test_content_always_populated(self, mock_db_path):
        """Verify content field is always present and populated on success."""
        from waggle.database import init_schema
        init_schema(str(mock_db_path))
        self._insert_session(str(mock_db_path), "$1", "agent1")

        with patch("waggle.server.capture_pane", new_callable=AsyncMock) as mock_capture, \
             patch("waggle.server.state_parser.parse") as mock_parse:
            mock_capture.return_value = {"status": "success", "content": "actual pane text here"}
            mock_parse.return_value = ("working", None)

            result = await read_pane("$1")

        assert result["status"] == "success"
        assert "content" in result
        assert result["content"] == "actual pane text here"

    @pytest.mark.asyncio
    async def test_prompt_data_none_for_working(self, mock_db_path):
        """Verify prompt_data is None for working state."""
        from waggle.database import init_schema
        init_schema(str(mock_db_path))
        self._insert_session(str(mock_db_path), "$1", "agent1")

        with patch("waggle.server.capture_pane", new_callable=AsyncMock) as mock_capture, \
             patch("waggle.server.state_parser.parse") as mock_parse:
            mock_capture.return_value = {"status": "success", "content": "content"}
            mock_parse.return_value = ("working", None)

            result = await read_pane("$1")

        assert result["prompt_data"] is None

    @pytest.mark.asyncio
    async def test_prompt_data_none_for_done(self, mock_db_path):
        """Verify prompt_data is None for done state."""
        from waggle.database import init_schema
        init_schema(str(mock_db_path))
        self._insert_session(str(mock_db_path), "$1", "agent1")

        with patch("waggle.server.capture_pane", new_callable=AsyncMock) as mock_capture, \
             patch("waggle.server.state_parser.parse") as mock_parse:
            mock_capture.return_value = {"status": "success", "content": ">"}
            mock_parse.return_value = ("done", None)

            result = await read_pane("$1")

        assert result["prompt_data"] is None

    @pytest.mark.asyncio
    async def test_prompt_data_none_for_unknown(self, mock_db_path):
        """Verify prompt_data is None for unknown state."""
        from waggle.database import init_schema
        init_schema(str(mock_db_path))
        self._insert_session(str(mock_db_path), "$1", "agent1")

        with patch("waggle.server.capture_pane", new_callable=AsyncMock) as mock_capture, \
             patch("waggle.server.state_parser.parse") as mock_parse:
            mock_capture.return_value = {"status": "success", "content": "noise"}
            mock_parse.return_value = ("unknown", None)

            result = await read_pane("$1")

        assert result["prompt_data"] is None

    @pytest.mark.asyncio
    async def test_prompt_data_populated_for_ask_user(self, mock_db_path):
        """Verify prompt_data is not None for ask_user state."""
        from waggle.database import init_schema
        init_schema(str(mock_db_path))
        self._insert_session(str(mock_db_path), "$1", "agent1")

        prompt_data = {"question": "Which option?", "options": []}

        with patch("waggle.server.capture_pane", new_callable=AsyncMock) as mock_capture, \
             patch("waggle.server.state_parser.parse") as mock_parse:
            mock_capture.return_value = {"status": "success", "content": "content"}
            mock_parse.return_value = ("ask_user", prompt_data)

            result = await read_pane("$1")

        assert result["prompt_data"] is not None
        assert result["prompt_data"]["question"] == "Which option?"

    @pytest.mark.asyncio
    async def test_prompt_data_populated_for_check_permission(self, mock_db_path):
        """Verify prompt_data is not None for check_permission state."""
        from waggle.database import init_schema
        init_schema(str(mock_db_path))
        self._insert_session(str(mock_db_path), "$1", "agent1")

        prompt_data = {"tool_type": "Bash", "command": "ls", "description": "List files"}

        with patch("waggle.server.capture_pane", new_callable=AsyncMock) as mock_capture, \
             patch("waggle.server.state_parser.parse") as mock_parse:
            mock_capture.return_value = {"status": "success", "content": "content"}
            mock_parse.return_value = ("check_permission", prompt_data)

            result = await read_pane("$1")

        assert result["prompt_data"] is not None
        assert result["prompt_data"]["tool_type"] == "Bash"

    @pytest.mark.asyncio
    async def test_tmux_capture_failure_returns_error(self, mock_db_path):
        """Verify tmux capture failure returns error dict, not a crash."""
        from waggle.database import init_schema
        init_schema(str(mock_db_path))
        self._insert_session(str(mock_db_path), "$1", "agent1")

        with patch("waggle.server.capture_pane", new_callable=AsyncMock) as mock_capture:
            mock_capture.return_value = {"status": "error", "message": "pane not found"}

            result = await read_pane("$1")

        assert result["status"] == "error"
        assert "pane not found" in result["message"]

    @pytest.mark.asyncio
    async def test_scrollback_passed_through(self, mock_db_path):
        """Verify scrollback parameter is forwarded to capture_pane."""
        from waggle.database import init_schema
        init_schema(str(mock_db_path))
        self._insert_session(str(mock_db_path), "$1", "agent1")

        with patch("waggle.server.capture_pane", new_callable=AsyncMock) as mock_capture, \
             patch("waggle.server.state_parser.parse") as mock_parse:
            mock_capture.return_value = {"status": "success", "content": "content"}
            mock_parse.return_value = ("done", None)

            await read_pane("$1", scrollback=200)

        mock_capture.assert_called_once_with("$1", None, 200)

    @pytest.mark.asyncio
    async def test_pane_id_omitted_passes_none_to_capture(self, mock_db_path):
        """Verify pane_id defaults to None and is passed as None to capture_pane."""
        from waggle.database import init_schema
        init_schema(str(mock_db_path))
        self._insert_session(str(mock_db_path), "$1", "agent1")

        with patch("waggle.server.capture_pane", new_callable=AsyncMock) as mock_capture, \
             patch("waggle.server.state_parser.parse") as mock_parse:
            mock_capture.return_value = {"status": "success", "content": "content"}
            mock_parse.return_value = ("done", None)

            await read_pane("$1")

        mock_capture.assert_called_once_with("$1", None, 50)

    @pytest.mark.asyncio
    async def test_pane_id_provided_passed_to_capture(self, mock_db_path):
        """Verify provided pane_id is forwarded to capture_pane."""
        from waggle.database import init_schema
        init_schema(str(mock_db_path))
        self._insert_session(str(mock_db_path), "$1", "agent1")

        with patch("waggle.server.capture_pane", new_callable=AsyncMock) as mock_capture, \
             patch("waggle.server.state_parser.parse") as mock_parse:
            mock_capture.return_value = {"status": "success", "content": "content"}
            mock_parse.return_value = ("done", None)

            await read_pane("$1", pane_id="%3")

        mock_capture.assert_called_once_with("$1", "%3", 50)

    @pytest.mark.asyncio
    async def test_invalid_pane_id_error_propagated(self, mock_db_path):
        """Verify capture_pane error from invalid pane_id propagates as error."""
        from waggle.database import init_schema
        init_schema(str(mock_db_path))
        self._insert_session(str(mock_db_path), "$1", "agent1")

        with patch("waggle.server.capture_pane", new_callable=AsyncMock) as mock_capture:
            mock_capture.return_value = {
                "status": "error",
                "message": "Pane '%99' does not belong to session '$1'",
            }

            result = await read_pane("$1", pane_id="%99")

        assert result["status"] == "error"
        assert "%99" in result["message"]


class TestSendCommand:
    """Tests for send_command() MCP tool — sending commands to agent panes."""

    def _insert_session(self, db_path: str, session_id: str, session_name: str) -> str:
        """Insert a state row and return the key."""
        key = f"{session_name}+{session_id}+1111111111"
        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO state (key, repo, status, updated_at) VALUES (?, ?, ?, ?)",
            (key, "/repo", "waiting", "2024-01-01T00:00:00"),
        )
        conn.commit()
        conn.close()
        return key

    @pytest.mark.asyncio
    async def test_unregistered_session_returns_error(self, mock_db_path):
        """Verify error when session_id has no DB entry."""
        from waggle.database import init_schema
        init_schema(str(mock_db_path))

        result = await send_command("$99", "hello")

        assert result["status"] == "error"
        assert "$99" in result["message"]

    @pytest.mark.asyncio
    async def test_happy_path_done_state_delivers_command(self, mock_db_path):
        """Verify command delivered to done-state agent, returns success."""
        from waggle.database import init_schema
        init_schema(str(mock_db_path))
        self._insert_session(str(mock_db_path), "$1", "agent1")

        with patch("waggle.server.capture_pane", new_callable=AsyncMock) as mock_capture, \
             patch("waggle.server.state_parser.parse") as mock_parse, \
             patch("waggle.server.clear_pane_input", new_callable=AsyncMock) as mock_clear, \
             patch("waggle.server.send_keys_to_pane", new_callable=AsyncMock) as mock_send:
            # First capture returns done state; second capture (poll) returns different state
            mock_capture.side_effect = [
                {"status": "success", "content": "> "},
                {"status": "success", "content": "working..."},
            ]
            mock_parse.side_effect = [("done", None), ("working", None)]
            mock_clear.return_value = {"status": "success"}
            mock_send.return_value = {"status": "success"}

            result = await send_command("$1", "run tests")

        assert result["status"] == "success"
        assert "delivered" in result["message"]

    @pytest.mark.asyncio
    async def test_working_state_returns_busy_error(self, mock_db_path):
        """Verify 'agent is busy' error returned when agent is in working state."""
        from waggle.database import init_schema
        init_schema(str(mock_db_path))
        self._insert_session(str(mock_db_path), "$1", "agent1")

        with patch("waggle.server.capture_pane", new_callable=AsyncMock) as mock_capture, \
             patch("waggle.server.state_parser.parse") as mock_parse:
            mock_capture.return_value = {"status": "success", "content": "Esc to interrupt"}
            mock_parse.return_value = ("working", None)

            result = await send_command("$1", "hello")

        assert result["status"] == "error"
        assert result["message"] == "agent is busy"

    @pytest.mark.asyncio
    async def test_unknown_state_returns_safe_send_error(self, mock_db_path):
        """Verify 'agent state unknown' error returned for unknown state."""
        from waggle.database import init_schema
        init_schema(str(mock_db_path))
        self._insert_session(str(mock_db_path), "$1", "agent1")

        with patch("waggle.server.capture_pane", new_callable=AsyncMock) as mock_capture, \
             patch("waggle.server.state_parser.parse") as mock_parse:
            mock_capture.return_value = {"status": "success", "content": "???"}
            mock_parse.return_value = ("unknown", None)

            result = await send_command("$1", "hello")

        assert result["status"] == "error"
        assert result["message"] == "agent state unknown, cannot safely send"

    @pytest.mark.asyncio
    async def test_ask_user_valid_option_accepted(self, mock_db_path):
        """Verify valid option number is accepted and sent for ask_user state."""
        from waggle.database import init_schema
        init_schema(str(mock_db_path))
        self._insert_session(str(mock_db_path), "$1", "agent1")

        prompt_data = {
            "question": "Choose one",
            "options": [
                {"number": "1", "label": "Yes"},
                {"number": "2", "label": "No"},
            ],
        }

        with patch("waggle.server.capture_pane", new_callable=AsyncMock) as mock_capture, \
             patch("waggle.server.state_parser.parse") as mock_parse, \
             patch("waggle.server.clear_pane_input", new_callable=AsyncMock) as mock_clear, \
             patch("waggle.server.send_keys_to_pane", new_callable=AsyncMock) as mock_send:
            mock_capture.side_effect = [
                {"status": "success", "content": "prompt"},
                {"status": "success", "content": "working"},
            ]
            mock_parse.side_effect = [("ask_user", prompt_data), ("working", None)]
            mock_clear.return_value = {"status": "success"}
            mock_send.return_value = {"status": "success"}

            result = await send_command("$1", "1")

        assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_ask_user_invalid_option_rejected(self, mock_db_path):
        """Verify invalid option number rejected with descriptive error for ask_user state."""
        from waggle.database import init_schema
        init_schema(str(mock_db_path))
        self._insert_session(str(mock_db_path), "$1", "agent1")

        prompt_data = {
            "question": "Choose one",
            "options": [
                {"number": "1", "label": "Yes"},
                {"number": "2", "label": "No"},
            ],
        }

        with patch("waggle.server.capture_pane", new_callable=AsyncMock) as mock_capture, \
             patch("waggle.server.state_parser.parse") as mock_parse:
            mock_capture.return_value = {"status": "success", "content": "prompt"}
            mock_parse.return_value = ("ask_user", prompt_data)

            result = await send_command("$1", "99")

        assert result["status"] == "error"
        assert "99" in result["message"]
        assert "invalid option" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_check_permission_1_accepted(self, mock_db_path):
        """Verify '1' is accepted as valid response for check_permission state."""
        from waggle.database import init_schema
        init_schema(str(mock_db_path))
        self._insert_session(str(mock_db_path), "$1", "agent1")

        with patch("waggle.server.capture_pane", new_callable=AsyncMock) as mock_capture, \
             patch("waggle.server.state_parser.parse") as mock_parse, \
             patch("waggle.server.clear_pane_input", new_callable=AsyncMock) as mock_clear, \
             patch("waggle.server.send_keys_to_pane", new_callable=AsyncMock) as mock_send:
            mock_capture.side_effect = [
                {"status": "success", "content": "permission prompt"},
                {"status": "success", "content": "working"},
            ]
            mock_parse.side_effect = [("check_permission", {"tool_type": "Bash"}), ("working", None)]
            mock_clear.return_value = {"status": "success"}
            mock_send.return_value = {"status": "success"}

            result = await send_command("$1", "1")

        assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_check_permission_2_accepted(self, mock_db_path):
        """Verify '2' is accepted as valid response for check_permission state."""
        from waggle.database import init_schema
        init_schema(str(mock_db_path))
        self._insert_session(str(mock_db_path), "$1", "agent1")

        with patch("waggle.server.capture_pane", new_callable=AsyncMock) as mock_capture, \
             patch("waggle.server.state_parser.parse") as mock_parse, \
             patch("waggle.server.clear_pane_input", new_callable=AsyncMock) as mock_clear, \
             patch("waggle.server.send_keys_to_pane", new_callable=AsyncMock) as mock_send:
            mock_capture.side_effect = [
                {"status": "success", "content": "permission prompt"},
                {"status": "success", "content": "done"},
            ]
            mock_parse.side_effect = [("check_permission", {"tool_type": "Bash"}), ("done", None)]
            mock_clear.return_value = {"status": "success"}
            mock_send.return_value = {"status": "success"}

            result = await send_command("$1", "2")

        assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_check_permission_invalid_value_rejected(self, mock_db_path):
        """Verify values other than '1'/'2' rejected for check_permission state."""
        from waggle.database import init_schema
        init_schema(str(mock_db_path))
        self._insert_session(str(mock_db_path), "$1", "agent1")

        with patch("waggle.server.capture_pane", new_callable=AsyncMock) as mock_capture, \
             patch("waggle.server.state_parser.parse") as mock_parse:
            mock_capture.return_value = {"status": "success", "content": "permission prompt"}
            mock_parse.return_value = ("check_permission", {"tool_type": "Bash"})

            result = await send_command("$1", "yes")

        assert result["status"] == "error"
        assert "invalid option" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_check_permission_3_rejected(self, mock_db_path):
        """Verify '3' is rejected for check_permission state."""
        from waggle.database import init_schema
        init_schema(str(mock_db_path))
        self._insert_session(str(mock_db_path), "$1", "agent1")

        with patch("waggle.server.capture_pane", new_callable=AsyncMock) as mock_capture, \
             patch("waggle.server.state_parser.parse") as mock_parse:
            mock_capture.return_value = {"status": "success", "content": "permission prompt"}
            mock_parse.return_value = ("check_permission", {"tool_type": "Bash"})

            result = await send_command("$1", "3")

        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_delivery_verified_via_state_transition(self, mock_db_path):
        """Verify success returned once state transitions from initial state."""
        from waggle.database import init_schema
        init_schema(str(mock_db_path))
        self._insert_session(str(mock_db_path), "$1", "agent1")

        with patch("waggle.server.capture_pane", new_callable=AsyncMock) as mock_capture, \
             patch("waggle.server.state_parser.parse") as mock_parse, \
             patch("waggle.server.clear_pane_input", new_callable=AsyncMock) as mock_clear, \
             patch("waggle.server.send_keys_to_pane", new_callable=AsyncMock) as mock_send, \
             patch("waggle.server.asyncio.sleep", new_callable=AsyncMock):
            # Initial capture: done; then 2 polls staying same, 3rd poll transitions
            mock_capture.side_effect = [
                {"status": "success", "content": "> "},
                {"status": "success", "content": "> "},
                {"status": "success", "content": "> "},
                {"status": "success", "content": "working..."},
            ]
            mock_parse.side_effect = [
                ("done", None),
                ("done", None),
                ("done", None),
                ("working", None),
            ]
            mock_clear.return_value = {"status": "success"}
            mock_send.return_value = {"status": "success"}

            result = await send_command("$1", "run tests")

        assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_timeout_returns_error_no_retry(self, mock_db_path):
        """Verify timeout after 5s returns error without retrying the send."""
        from waggle.database import init_schema
        init_schema(str(mock_db_path))
        self._insert_session(str(mock_db_path), "$1", "agent1")

        with patch("waggle.server.capture_pane", new_callable=AsyncMock) as mock_capture, \
             patch("waggle.server.state_parser.parse") as mock_parse, \
             patch("waggle.server.clear_pane_input", new_callable=AsyncMock) as mock_clear, \
             patch("waggle.server.send_keys_to_pane", new_callable=AsyncMock) as mock_send, \
             patch("waggle.server.asyncio.sleep", new_callable=AsyncMock):
            # All captures return same state — no transition
            mock_capture.return_value = {"status": "success", "content": "> "}
            mock_parse.return_value = ("done", None)
            mock_clear.return_value = {"status": "success"}
            mock_send.return_value = {"status": "success"}

            result = await send_command("$1", "run tests")

        # send_keys_to_pane called exactly once (no retry)
        assert mock_send.call_count == 1
        assert result["status"] == "error"
        assert "unconfirmed" in result["message"].lower() or "timeout" in result["message"].lower() or "5 seconds" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_specific_pane_id_forwarded(self, mock_db_path):
        """Verify pane_id is forwarded to capture_pane, clear_pane_input, and send_keys_to_pane."""
        from waggle.database import init_schema
        init_schema(str(mock_db_path))
        self._insert_session(str(mock_db_path), "$1", "agent1")

        with patch("waggle.server.capture_pane", new_callable=AsyncMock) as mock_capture, \
             patch("waggle.server.state_parser.parse") as mock_parse, \
             patch("waggle.server.clear_pane_input", new_callable=AsyncMock) as mock_clear, \
             patch("waggle.server.send_keys_to_pane", new_callable=AsyncMock) as mock_send:
            mock_capture.side_effect = [
                {"status": "success", "content": "> "},
                {"status": "success", "content": "working"},
            ]
            mock_parse.side_effect = [("done", None), ("working", None)]
            mock_clear.return_value = {"status": "success"}
            mock_send.return_value = {"status": "success"}

            result = await send_command("$1", "cmd", pane_id="%5")

        mock_capture.assert_any_call("$1", "%5")
        mock_clear.assert_called_once_with("$1", "%5")
        mock_send.assert_called_once_with("$1", "cmd", "%5")
        assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_capture_failure_returns_error(self, mock_db_path):
        """Verify capture_pane failure is propagated as error."""
        from waggle.database import init_schema
        init_schema(str(mock_db_path))
        self._insert_session(str(mock_db_path), "$1", "agent1")

        with patch("waggle.server.capture_pane", new_callable=AsyncMock) as mock_capture:
            mock_capture.return_value = {"status": "error", "message": "pane not found"}

            result = await send_command("$1", "cmd")

        assert result["status"] == "error"
        assert "pane not found" in result["message"]

    @pytest.mark.asyncio
    async def test_ask_user_valid_option_does_not_send_ctrl_c(self, mock_db_path):
        """Verify clear_pane_input (Ctrl+C) is NOT called for ask_user state."""
        from waggle.database import init_schema
        init_schema(str(mock_db_path))
        self._insert_session(str(mock_db_path), "$1", "agent1")

        prompt_data = {
            "question": "Choose one",
            "options": [
                {"number": 1, "label": "Yes"},
                {"number": 2, "label": "No"},
            ],
        }

        with patch("waggle.server.capture_pane", new_callable=AsyncMock) as mock_capture, \
             patch("waggle.server.state_parser.parse") as mock_parse, \
             patch("waggle.server.clear_pane_input", new_callable=AsyncMock) as mock_clear, \
             patch("waggle.server.send_keys_to_pane", new_callable=AsyncMock) as mock_send:
            mock_capture.side_effect = [
                {"status": "success", "content": "prompt"},
                {"status": "success", "content": "working"},
            ]
            mock_parse.side_effect = [("ask_user", prompt_data), ("working", None)]
            mock_send.return_value = {"status": "success"}

            result = await send_command("$1", "1")

        assert result["status"] == "success"
        mock_clear.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("command", ["1", "2"])
    async def test_check_permission_does_not_send_ctrl_c(self, mock_db_path, command):
        """Verify clear_pane_input (Ctrl+C) is NOT called for check_permission state."""
        from waggle.database import init_schema
        init_schema(str(mock_db_path))
        self._insert_session(str(mock_db_path), "$1", "agent1")

        with patch("waggle.server.capture_pane", new_callable=AsyncMock) as mock_capture, \
             patch("waggle.server.state_parser.parse") as mock_parse, \
             patch("waggle.server.clear_pane_input", new_callable=AsyncMock) as mock_clear, \
             patch("waggle.server.send_keys_to_pane", new_callable=AsyncMock) as mock_send:
            mock_capture.side_effect = [
                {"status": "success", "content": "permission prompt"},
                {"status": "success", "content": "working"},
            ]
            mock_parse.side_effect = [("check_permission", {"tool_type": "Bash"}), ("working", None)]
            mock_send.return_value = {"status": "success"}

            result = await send_command("$1", command)

        assert result["status"] == "success"
        mock_clear.assert_not_called()

    @pytest.mark.asyncio
    async def test_done_state_does_send_ctrl_c(self, mock_db_path):
        """Verify clear_pane_input (Ctrl+C) IS called for done state (normal path preserved)."""
        from waggle.database import init_schema
        init_schema(str(mock_db_path))
        self._insert_session(str(mock_db_path), "$1", "agent1")

        with patch("waggle.server.capture_pane", new_callable=AsyncMock) as mock_capture, \
             patch("waggle.server.state_parser.parse") as mock_parse, \
             patch("waggle.server.clear_pane_input", new_callable=AsyncMock) as mock_clear, \
             patch("waggle.server.send_keys_to_pane", new_callable=AsyncMock) as mock_send:
            mock_capture.side_effect = [
                {"status": "success", "content": "> "},
                {"status": "success", "content": "working..."},
            ]
            mock_parse.side_effect = [("done", None), ("working", None)]
            mock_clear.return_value = {"status": "success"}
            mock_send.return_value = {"status": "success"}

            result = await send_command("$1", "run tests")

        assert result["status"] == "success"
        mock_clear.assert_called_once_with("$1", None)

    @pytest.mark.asyncio
    async def test_custom_text_sends_option_without_enter_then_text_with_enter(self, mock_db_path):
        """Verify custom_text sends option without Enter, then custom_text with Enter."""
        from waggle.database import init_schema
        init_schema(str(mock_db_path))
        self._insert_session(str(mock_db_path), "$1", "agent1")

        prompt_data = {
            "question": "What is your favorite color?",
            "options": [
                {"number": 1, "label": "Red", "description": ""},
                {"number": 2, "label": "Blue", "description": ""},
                {"number": 3, "label": "Type something.", "description": ""},
            ],
        }

        with patch("waggle.server.capture_pane", new_callable=AsyncMock) as mock_capture, \
             patch("waggle.server.state_parser.parse") as mock_parse, \
             patch("waggle.server.send_keys_to_pane", new_callable=AsyncMock) as mock_send:
            mock_capture.side_effect = [
                {"status": "success", "content": "ask prompt"},
                {"status": "success", "content": "working"},
            ]
            mock_parse.side_effect = [("ask_user", prompt_data), ("working", None)]
            mock_send.return_value = {"status": "success"}

            result = await send_command("$1", "3", custom_text="teddybear")

        assert result["status"] == "success"
        assert mock_send.call_count == 2
        first_call = mock_send.call_args_list[0]
        second_call = mock_send.call_args_list[1]
        # First call: option number without Enter
        assert first_call.args[1] == "3"
        assert first_call.kwargs.get("enter") is False or first_call.args[3] is False
        # Second call: custom text with Enter (default)
        assert second_call.args[1] == "teddybear"

    @pytest.mark.asyncio
    async def test_custom_text_rejected_for_non_type_something_option(self, mock_db_path):
        """Verify custom_text is rejected when the selected option is not 'Type something.'."""
        from waggle.database import init_schema
        init_schema(str(mock_db_path))
        self._insert_session(str(mock_db_path), "$1", "agent1")

        prompt_data = {
            "question": "What is your favorite color?",
            "options": [
                {"number": 1, "label": "Red", "description": ""},
                {"number": 2, "label": "Type something.", "description": ""},
            ],
        }

        with patch("waggle.server.capture_pane", new_callable=AsyncMock) as mock_capture, \
             patch("waggle.server.state_parser.parse") as mock_parse:
            mock_capture.return_value = {"status": "success", "content": "ask prompt"}
            mock_parse.return_value = ("ask_user", prompt_data)

            result = await send_command("$1", "1", custom_text="teddybear")

        assert result["status"] == "error"
        assert "Type something" in result["message"]


class TestSpawnAgent:
    """Tests for spawn_agent() MCP tool — launching agents in tmux sessions."""

    def _get_db_session_keys(self, db_path: str) -> list[str]:
        """Fetch all keys from state table."""
        conn = sqlite3.connect(db_path)
        keys = [row[0] for row in conn.execute("SELECT key FROM state").fetchall()]
        conn.close()
        return keys

    @pytest.mark.asyncio
    async def test_invalid_agent_returns_error(self, mock_db_path):
        """Verify unsupported agent type is rejected immediately."""
        from waggle.database import init_schema
        init_schema(str(mock_db_path))

        result = await spawn_agent("/repo", "my-session", "gpt4")

        assert result["status"] == "error"
        assert "invalid agent" in result["message"].lower()
        assert result["session_id"] is None

    @pytest.mark.asyncio
    async def test_basic_spawn_no_command_success(self, mock_db_path):
        """Verify spawn without command: creates session, registers DB, returns immediately."""
        from waggle.database import init_schema
        init_schema(str(mock_db_path))

        with patch("waggle.server.resolve_session", new_callable=AsyncMock) as mock_resolve, \
             patch("waggle.server.create_session", new_callable=AsyncMock) as mock_create, \
             patch("waggle.server.launch_agent_in_pane", new_callable=AsyncMock) as mock_launch:
            mock_resolve.return_value = {"action": "create"}
            mock_create.return_value = {
                "status": "success",
                "session_id": "$5",
                "session_name": "my-session",
                "session_created": "1700000000",
            }
            mock_launch.return_value = {"status": "success"}

            result = await spawn_agent("/repo", "my-session", "claude")

        assert result["status"] == "success"
        assert result["session_id"] == "$5"
        assert result["session_name"] == "my-session"
        assert "launched" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_db_entry_registered_after_launch(self, mock_db_path):
        """Verify composite DB key is created with correct format after spawn."""
        from waggle.database import init_schema
        init_schema(str(mock_db_path))

        with patch("waggle.server.resolve_session", new_callable=AsyncMock) as mock_resolve, \
             patch("waggle.server.create_session", new_callable=AsyncMock) as mock_create, \
             patch("waggle.server.launch_agent_in_pane", new_callable=AsyncMock) as mock_launch:
            mock_resolve.return_value = {"action": "create"}
            mock_create.return_value = {
                "status": "success",
                "session_id": "$5",
                "session_name": "my-session",
                "session_created": "1700000000",
            }
            mock_launch.return_value = {"status": "success"}

            await spawn_agent("/repo", "my-session", "claude")

        keys = self._get_db_session_keys(str(mock_db_path))
        assert any("my-session" in k and "$5" in k and "1700000000" in k for k in keys)

    @pytest.mark.asyncio
    async def test_session_resolution_llm_running_returns_error(self, mock_db_path):
        """Verify error returned when session exists with LLM already running."""
        from waggle.database import init_schema
        init_schema(str(mock_db_path))

        with patch("waggle.server.resolve_session", new_callable=AsyncMock) as mock_resolve:
            mock_resolve.return_value = {
                "action": "error",
                "message": "LLM already running in session",
            }

            result = await spawn_agent("/repo", "existing-session", "claude")

        assert result["status"] == "error"
        assert "LLM already running" in result["message"]

    @pytest.mark.asyncio
    async def test_session_resolution_wrong_repo_returns_error(self, mock_db_path):
        """Verify error returned when session exists but in wrong repo."""
        from waggle.database import init_schema
        init_schema(str(mock_db_path))

        with patch("waggle.server.resolve_session", new_callable=AsyncMock) as mock_resolve:
            mock_resolve.return_value = {
                "action": "error",
                "message": "session exists but is in wrong repo",
            }

            result = await spawn_agent("/my/repo", "existing-session", "claude")

        assert result["status"] == "error"
        assert "wrong repo" in result["message"]

    @pytest.mark.asyncio
    async def test_reuse_existing_session(self, mock_db_path):
        """Verify reuse action launches agent in existing session without creating new one."""
        from waggle.database import init_schema
        init_schema(str(mock_db_path))

        with patch("waggle.server.resolve_session", new_callable=AsyncMock) as mock_resolve, \
             patch("waggle.server.create_session", new_callable=AsyncMock) as mock_create, \
             patch("waggle.server.launch_agent_in_pane", new_callable=AsyncMock) as mock_launch:
            mock_resolve.return_value = {
                "action": "reuse",
                "session_id": "$3",
                "session_name": "existing-session",
                "session_created": "1700000001",
            }
            mock_launch.return_value = {"status": "success"}

            result = await spawn_agent("/repo", "existing-session", "claude")

        mock_create.assert_not_called()
        assert result["status"] == "success"
        assert result["session_id"] == "$3"

    @pytest.mark.asyncio
    async def test_spawn_with_command_waits_and_delivers(self, mock_db_path):
        """Verify spawn with command polls until done state then delivers command."""
        from waggle.database import init_schema
        init_schema(str(mock_db_path))

        with patch("waggle.server.resolve_session", new_callable=AsyncMock) as mock_resolve, \
             patch("waggle.server.create_session", new_callable=AsyncMock) as mock_create, \
             patch("waggle.server.launch_agent_in_pane", new_callable=AsyncMock) as mock_launch, \
             patch("waggle.server.capture_pane", new_callable=AsyncMock) as mock_capture, \
             patch("waggle.server.state_parser.parse") as mock_parse, \
             patch("waggle.server.clear_pane_input", new_callable=AsyncMock) as mock_clear, \
             patch("waggle.server.send_keys_to_pane", new_callable=AsyncMock) as mock_send, \
             patch("waggle.server.asyncio.sleep", new_callable=AsyncMock):
            mock_resolve.return_value = {"action": "create"}
            mock_create.return_value = {
                "status": "success",
                "session_id": "$5",
                "session_name": "my-session",
                "session_created": "1700000000",
            }
            mock_launch.return_value = {"status": "success"}
            mock_capture.side_effect = [
                {"status": "success", "content": "loading..."},
                {"status": "success", "content": "loading..."},
                {"status": "success", "content": "> "},
            ]
            mock_parse.side_effect = [("working", None), ("working", None), ("done", None)]
            mock_clear.return_value = {"status": "success"}
            mock_send.return_value = {"status": "success"}

            result = await spawn_agent("/repo", "my-session", "claude", command="run tests")

        assert result["status"] == "success"
        assert "command delivered" in result["message"].lower()
        mock_send.assert_called_once_with("$5", "run tests")

    @pytest.mark.asyncio
    async def test_readiness_timeout_returns_error_with_last_state(self, mock_db_path):
        """Verify 60s timeout returns error with last known state included."""
        from waggle.database import init_schema
        init_schema(str(mock_db_path))

        with patch("waggle.server.resolve_session", new_callable=AsyncMock) as mock_resolve, \
             patch("waggle.server.create_session", new_callable=AsyncMock) as mock_create, \
             patch("waggle.server.launch_agent_in_pane", new_callable=AsyncMock) as mock_launch, \
             patch("waggle.server.capture_pane", new_callable=AsyncMock) as mock_capture, \
             patch("waggle.server.state_parser.parse") as mock_parse, \
             patch("waggle.server.asyncio.sleep", new_callable=AsyncMock):
            mock_resolve.return_value = {"action": "create"}
            mock_create.return_value = {
                "status": "success",
                "session_id": "$5",
                "session_name": "my-session",
                "session_created": "1700000000",
            }
            mock_launch.return_value = {"status": "success"}
            # Never reaches done state
            mock_capture.return_value = {"status": "success", "content": "loading..."}
            mock_parse.return_value = ("working", None)

            result = await spawn_agent("/repo", "my-session", "claude", command="run tests")

        assert result["status"] == "error"
        assert "timeout" in result["message"].lower() or "60s" in result["message"]
        assert "working" in result["message"]

    @pytest.mark.asyncio
    async def test_return_contract_all_fields_present(self, mock_db_path):
        """Verify all return paths include {status, session_id, session_name, message}."""
        from waggle.database import init_schema
        init_schema(str(mock_db_path))

        with patch("waggle.server.resolve_session", new_callable=AsyncMock) as mock_resolve, \
             patch("waggle.server.create_session", new_callable=AsyncMock) as mock_create, \
             patch("waggle.server.launch_agent_in_pane", new_callable=AsyncMock) as mock_launch:
            mock_resolve.return_value = {"action": "create"}
            mock_create.return_value = {
                "status": "success",
                "session_id": "$5",
                "session_name": "my-session",
                "session_created": "1700000000",
            }
            mock_launch.return_value = {"status": "success"}

            result = await spawn_agent("/repo", "my-session", "claude")

        assert "status" in result
        assert "session_id" in result
        assert "session_name" in result
        assert "message" in result
