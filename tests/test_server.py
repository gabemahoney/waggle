"""Unit tests for MCP server initialization and startup."""

import json
import os
import sqlite3
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock, call, AsyncMock

import pytest

from waggle import server
from waggle.server import (
    startup, mcp, resolve_repo_root, get_client_repo_root, cleanup_dead_sessions,
    TMUX_FIELD_SEP
)

# Shorthand for building mock tmux output lines
SEP = TMUX_FIELD_SEP

# Access underlying functions from decorated tools
list_agents = server.list_agents.fn
delete_repo_agents = server.delete_repo_agents.fn


# Pytest fixtures for common mock patterns
@pytest.fixture
def mock_ctx():
    """Fixture for mocked FastMCP context."""
    ctx = AsyncMock()
    ctx.list_roots = AsyncMock(return_value=[])
    return ctx


@pytest.fixture
def mock_tmux_subprocess():
    """Fixture for mocking tmux subprocess.run calls."""
    with patch('waggle.server.subprocess.run') as mock_run:
        yield mock_run


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
    
    def test_cleanup_dead_sessions_removes_orphaned_entries(self, mock_db_path, mock_tmux_subprocess, mock_db_connection):
        """Verify cleanup_dead_sessions removes database entries for dead tmux sessions."""
        mock_conn, mock_cursor = mock_db_connection
        
        # Mock tmux returning only one active session
        mock_tmux_subprocess.return_value = MagicMock(
            returncode=0,
            stdout=f"active-session{SEP}$0{SEP}1234567890\n",
            stderr=""
        )
        
        # Database has entries for active and dead sessions (new key format without namespace)
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
    
    def test_cleanup_dead_sessions_handles_no_tmux_sessions(self, mock_tmux_subprocess):
        """Verify cleanup_dead_sessions handles no tmux server gracefully."""
        mock_tmux_subprocess.return_value = MagicMock(returncode=1, stderr="no server running")
        
        # Should not raise exception
        cleanup_dead_sessions()
    
    def test_cleanup_dead_sessions_handles_database_errors(self, mock_db_path, mock_tmux_subprocess):
        """Verify cleanup_dead_sessions silently handles database errors."""
        mock_tmux_subprocess.return_value = MagicMock(returncode=0, stdout=f"session{SEP}$0{SEP}123\n")
        
        with patch('waggle.server.connection') as mock_conn:
            mock_conn.side_effect = Exception("Database error")
            
            # Should not raise exception
            cleanup_dead_sessions()
    
    def test_cleanup_dead_sessions_preserves_active_sessions(self, mock_db_path, mock_tmux_subprocess, mock_db_connection):
        """Verify cleanup_dead_sessions doesn't delete entries for active sessions."""
        mock_conn, mock_cursor = mock_db_connection
        
        mock_tmux_subprocess.return_value = MagicMock(
            returncode=0,
            stdout=f"session1{SEP}$0{SEP}111\nsession2{SEP}$1{SEP}222\n",
            stderr=""
        )
        
        mock_cursor.fetchall.return_value = [
            ("session1+$0+111",),
            ("session2+$1+222",)
        ]
        
        cleanup_dead_sessions()
        
        # Verify no DELETE calls for active sessions
        delete_calls = [call for call in mock_cursor.execute.call_args_list 
                       if 'DELETE' in str(call)]
        assert len(delete_calls) == 0
    
    def test_cleanup_dead_sessions_only_removes_orphaned_entries(self, mock_db_path, mock_tmux_subprocess, mock_db_connection):
        """Verify cleanup_dead_sessions only removes dead session entries, not duplicates."""
        mock_conn, mock_cursor = mock_db_connection
        
        # Mock tmux returning one active session
        mock_tmux_subprocess.return_value = MagicMock(
            returncode=0,
            stdout=f"test-session{SEP}$3{SEP}1234567890\n",
            stderr=""
        )
        
        # New schema: keys without namespace prefix
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
    async def test_list_agents_returns_empty_when_no_sessions(self, mock_ctx, mock_cleanup, mock_tmux_subprocess, mock_db_path, mock_db_connection):
        """Verify list_agents returns empty list when no DB entries exist."""
        mock_conn, mock_cursor = mock_db_connection
        
        # Simulate "no server running" error
        mock_tmux_subprocess.side_effect = subprocess.CalledProcessError(
            1, ["tmux"], stderr="no server running"
        )
        
        mock_cursor.fetchall.return_value = []  # No DB entries
        
        result = await list_agents(ctx=mock_ctx)
        
        assert result["status"] == "success"
        assert result["agents"] == []
    
    @pytest.mark.asyncio
    async def test_list_agents_excludes_sessions_without_db_entries(self, mock_ctx, mock_cleanup, mock_tmux_subprocess, mock_db_path, mock_db_connection):
        """Verify list_agents excludes sessions without DB entries (DB as source of truth)."""
        mock_conn, mock_cursor = mock_db_connection
        
        # Mock tmux list-sessions output
        mock_tmux_subprocess.return_value = MagicMock(
            returncode=0,
            stdout=f"session1{SEP}$0{SEP}1234567890{SEP}/path1\nsession2{SEP}$1{SEP}1234567891{SEP}/path2\n",
            stderr=""
        )
        
        mock_cursor.fetchall.return_value = []  # No db entries
        
        result = await list_agents(ctx=mock_ctx)
        
        assert result["status"] == "success"
        assert len(result["agents"]) == 0  # No agents returned because none are registered in DB
    
    @pytest.mark.asyncio
    async def test_list_agents_matches_status_from_database(self, tmp_path, mock_ctx, mock_cleanup, mock_tmux_subprocess, mock_db_path, mock_db_connection):
        """Verify list_agents matches tmux sessions with database state."""
        mock_conn, mock_cursor = mock_db_connection
        
        mock_tmux_subprocess.return_value = MagicMock(
            returncode=0,
            stdout=f"agent1{SEP}$0{SEP}1234567890{SEP}/path1\nagent2{SEP}$1{SEP}1234567891{SEP}/path2\n",
            stderr=""
        )
        
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
    async def test_list_agents_filters_by_name(self, mock_ctx, mock_cleanup, mock_tmux_subprocess, mock_db_path, mock_db_connection):
        """Verify list_agents filters sessions by name parameter."""
        mock_conn, mock_cursor = mock_db_connection
        
        mock_tmux_subprocess.return_value = MagicMock(
            returncode=0,
            stdout=f"agent1{SEP}$0{SEP}1234567890{SEP}/path1\nagent2{SEP}$1{SEP}1234567891{SEP}/path2\nagent3{SEP}$2{SEP}1234567892{SEP}/path3\n",
            stderr=""
        )
        
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
    async def test_list_agents_returns_error_on_database_failure(self, mock_ctx, mock_cleanup, mock_tmux_subprocess, mock_db_path):
        """Verify list_agents returns error when database query fails."""
        mock_tmux_subprocess.return_value = MagicMock(
            returncode=0,
            stdout=f"agent1{SEP}$0{SEP}/path1\n",
            stderr=""
        )
        
        with patch('waggle.server.connection') as mock_conn:
            mock_conn.side_effect = Exception("Database unreachable")
            
            result = await list_agents(ctx=mock_ctx)
        
        assert result["status"] == "error"
        assert "Failed to query database" in result["error"]
    
    @pytest.mark.asyncio
    async def test_list_agents_handles_tmux_not_installed(self, mock_ctx, mock_cleanup, mock_tmux_subprocess, mock_db_path, mock_db_connection):
        """Verify list_agents returns DB agents even when tmux is not installed."""
        mock_conn, mock_cursor = mock_db_connection
        mock_tmux_subprocess.side_effect = FileNotFoundError()
        
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
    async def test_list_agents_handles_tmux_timeout(self, mock_ctx, mock_cleanup, mock_tmux_subprocess, mock_db_path, mock_db_connection):
        """Verify list_agents returns DB agents even when tmux command times out."""
        mock_conn, mock_cursor = mock_db_connection
        mock_tmux_subprocess.side_effect = subprocess.TimeoutExpired(
            cmd=["tmux", "list-sessions"],
            timeout=5
        )
        
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
    async def test_list_agents_includes_namespace_field(self, mock_ctx, mock_cleanup, mock_tmux_subprocess, mock_db_path, mock_db_connection):
        """Verify list_agents includes namespace field in output."""
        mock_conn, mock_cursor = mock_db_connection
        
        mock_tmux_subprocess.return_value = MagicMock(
            returncode=0,
            stdout=f"agent1{SEP}$0{SEP}1234567890{SEP}/path1\nagent2{SEP}$1{SEP}1234567891{SEP}/path2\n",
            stderr=""
        )
        
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
    async def test_list_agents_namespace_none_when_no_state(self, mock_ctx, mock_cleanup, mock_tmux_subprocess, mock_db_path, mock_db_connection):
        """Verify list_agents returns empty when no database entries (DB as source of truth)."""
        mock_conn, mock_cursor = mock_db_connection
        
        mock_tmux_subprocess.return_value = MagicMock(
            returncode=0,
            stdout=f"agent1{SEP}$0{SEP}1234567890{SEP}/path1\n",
            stderr=""
        )
        
        mock_cursor.fetchall.return_value = []  # No db entries
        
        result = await list_agents(ctx=mock_ctx)
        
        assert result["status"] == "success"
        assert len(result["agents"]) == 0  # No agents because none registered in DB
    
    @pytest.mark.asyncio
    async def test_list_agents_filters_by_repo(self, mock_ctx, mock_cleanup, mock_tmux_subprocess, mock_db_path, mock_db_connection):
        """Verify list_agents filters by repo parameter (case-insensitive)."""
        mock_conn, mock_cursor = mock_db_connection
        
        mock_tmux_subprocess.return_value = MagicMock(
            returncode=0,
            stdout=f"agent1{SEP}$0{SEP}1234567890{SEP}/path1\nagent2{SEP}$1{SEP}1234567891{SEP}/path2\nagent3{SEP}$2{SEP}1234567892{SEP}/path3\n",
            stderr=""
        )
        
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
    async def test_list_agents_filters_by_repo_case_insensitive(self, mock_ctx, mock_cleanup, mock_tmux_subprocess, mock_db_path, mock_db_connection):
        """Verify list_agents repo filter is case-insensitive."""
        mock_conn, mock_cursor = mock_db_connection
        
        mock_tmux_subprocess.return_value = MagicMock(
            returncode=0,
            stdout=f"agent1{SEP}$0{SEP}1234567890{SEP}/path1\nagent2{SEP}$1{SEP}1234567891{SEP}/path2\n",
            stderr=""
        )
        
        mock_cursor.fetchall.return_value = [
            ("agent1+$0+1234567890", "/Projects/WAGGLE", "working"),
            ("agent2+$1+1234567891", "/projects/other", "waiting")
        ]
        
        result = await list_agents(repo="waggle", ctx=mock_ctx)
        
        assert result["status"] == "success"
        assert len(result["agents"]) == 1
        assert result["agents"][0]["name"] == "agent1"
    
    @pytest.mark.asyncio
    async def test_list_agents_repo_filter_excludes_none_namespace(self, mock_ctx, mock_cleanup, mock_tmux_subprocess, mock_db_path, mock_db_connection):
        """Verify list_agents repo filter excludes sessions with None namespace."""
        mock_conn, mock_cursor = mock_db_connection
        
        mock_tmux_subprocess.return_value = MagicMock(
            returncode=0,
            stdout=f"agent1{SEP}$0{SEP}1234567890{SEP}/path1\nagent2{SEP}$1{SEP}1234567891{SEP}/path2\n",
            stderr=""
        )
        
        # Only one agent has state, other will have None repo
        mock_cursor.fetchall.return_value = [
            ("agent1+$0+1234567890", "/projects/waggle", "working")
        ]
        
        result = await list_agents(repo="waggle", ctx=mock_ctx)
        
        assert result["status"] == "success"
        assert len(result["agents"]) == 1
        assert result["agents"][0]["name"] == "agent1"
    
    @pytest.mark.asyncio
    async def test_list_agents_without_repo_filter_returns_all(self, mock_ctx, mock_cleanup, mock_tmux_subprocess, mock_db_path, mock_db_connection):
        """Verify list_agents without repo parameter returns all DB-registered agents."""
        mock_conn, mock_cursor = mock_db_connection
        
        mock_tmux_subprocess.return_value = MagicMock(
            returncode=0,
            stdout=f"agent1{SEP}$0{SEP}1234567890{SEP}/path1\nagent2{SEP}$1{SEP}1234567891{SEP}/path2\nagent3{SEP}$2{SEP}1234567892{SEP}/path3\n",
            stderr=""
        )
        
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
    async def test_list_agents_excludes_unregistered_tmux_sessions(self, mock_ctx, mock_cleanup, mock_tmux_subprocess, mock_db_path, mock_db_connection):
        """Verify sessions without DB entries are excluded from list_agents output."""
        mock_conn, mock_cursor = mock_db_connection
        
        # Mock tmux with 3 sessions
        mock_tmux_subprocess.return_value = MagicMock(
            returncode=0,
            stdout=f"registered-agent{SEP}$0{SEP}1234567890{SEP}/projects/waggle\nunregistered-session{SEP}$1{SEP}1234567891{SEP}/random/path\nanother-unregistered{SEP}$2{SEP}1234567892{SEP}/other/path\n",
            stderr=""
        )
        
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
    async def test_list_agents_shows_custom_state_session_started(self, tmp_path, mock_ctx, mock_cleanup, mock_tmux_subprocess, mock_db_path, mock_db_connection):
        """Verify list_agents displays custom state 'session started'."""
        mock_conn, mock_cursor = mock_db_connection
        
        mock_tmux_subprocess.return_value = MagicMock(
            returncode=0,
            stdout=f"test-agent{SEP}$0{SEP}1234567890{SEP}/path1\n",
            stderr=""
        )
        
        mock_cursor.fetchall.return_value = [
            ("test-agent+$0+1234567890", str(tmp_path), "session started")
        ]
        
        result = await list_agents(ctx=mock_ctx)
        
        assert result["status"] == "success"
        assert len(result["agents"]) == 1
        assert result["agents"][0]["status"] == "session started"
    
    @pytest.mark.asyncio
    async def test_list_agents_shows_custom_state_need_permission(self, tmp_path, mock_ctx, mock_cleanup, mock_tmux_subprocess, mock_db_path, mock_db_connection):
        """Verify list_agents displays custom state 'need permission'."""
        mock_conn, mock_cursor = mock_db_connection
        
        mock_tmux_subprocess.return_value = MagicMock(
            returncode=0,
            stdout=f"agent2{SEP}$0{SEP}1234567890{SEP}/path1\n",
            stderr=""
        )
        
        mock_cursor.fetchall.return_value = [
            ("agent2+$0+1234567890", str(tmp_path), "need permission")
        ]
        
        result = await list_agents(ctx=mock_ctx)
        
        assert result["status"] == "success"
        assert len(result["agents"]) == 1
        assert result["agents"][0]["status"] == "need permission"
    
    @pytest.mark.asyncio
    async def test_list_agents_shows_custom_state_processing_data(self, tmp_path, mock_ctx, mock_cleanup, mock_tmux_subprocess, mock_db_path, mock_db_connection):
        """Verify list_agents displays custom state 'processing data'."""
        mock_conn, mock_cursor = mock_db_connection
        
        mock_tmux_subprocess.return_value = MagicMock(
            returncode=0,
            stdout=f"worker{SEP}$0{SEP}1234567890{SEP}/path1\n",
            stderr=""
        )
        
        mock_cursor.fetchall.return_value = [
            ("worker+$0+1234567890", str(tmp_path), "processing data")
        ]
        
        result = await list_agents(ctx=mock_ctx)
        
        assert result["status"] == "success"
        assert len(result["agents"]) == 1
        assert result["agents"][0]["status"] == "processing data"
    
    @pytest.mark.asyncio
    async def test_list_agents_multiple_agents_different_custom_states(self, tmp_path, mock_ctx, mock_cleanup, mock_tmux_subprocess, mock_db_path, mock_db_connection):
        """Verify list_agents correctly displays multiple agents with different custom states."""
        mock_conn, mock_cursor = mock_db_connection
        
        mock_tmux_subprocess.return_value = MagicMock(
            returncode=0,
            stdout=f"agent1{SEP}$0{SEP}1111111111{SEP}/path1\nagent2{SEP}$1{SEP}2222222222{SEP}/path2\nagent3{SEP}$2{SEP}3333333333{SEP}/path3\n",
            stderr=""
        )
        
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
    async def test_list_agents_custom_states_with_unknown_status(self, tmp_path, mock_ctx, mock_cleanup, mock_tmux_subprocess, mock_db_path, mock_db_connection):
        """Verify list_agents shows only DB-registered agents with custom states."""
        mock_conn, mock_cursor = mock_db_connection
        
        # Return 4 agents from tmux
        mock_tmux_subprocess.return_value = MagicMock(
            returncode=0,
            stdout=f"with-state1{SEP}$0{SEP}1111111111{SEP}/path1\nno-state{SEP}$1{SEP}2222222222{SEP}/path2\nwith-state2{SEP}$2{SEP}3333333333{SEP}/path3\nno-state2{SEP}$3{SEP}4444444444{SEP}/path4\n",
            stderr=""
        )
        
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
        
        # Mock tmux to return only the live session
        # Need to handle both cleanup_dead_sessions and list_agents calls
        def mock_tmux_run(*args, **kwargs):
            cmd = args[0] if args else kwargs.get('args', [])
            # Check format string to determine which call this is
            if '#{session_path}' in ' '.join(cmd):
                # list_agents call (4 fields)
                return MagicMock(
                    returncode=0,
                    stdout=f"live-agent{SEP}$0{SEP}1234567890{SEP}{namespace}\n",
                    stderr=""
                )
            else:
                # cleanup_dead_sessions call (3 fields)
                return MagicMock(
                    returncode=0,
                    stdout=f"live-agent{SEP}$0{SEP}1234567890\n",
                    stderr=""
                )
        
        with patch('waggle.server.subprocess.run', side_effect=mock_tmux_run):
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
        
        # Mock tmux
        def mock_tmux_run(*args, **kwargs):
            cmd = args[0] if args else kwargs.get('args', [])
            if '#{session_path}' in ' '.join(cmd):
                return MagicMock(
                    returncode=0,
                    stdout=f"persistent-agent{SEP}$0{SEP}1234567890{SEP}{namespace}\n",
                    stderr=""
                )
            else:
                return MagicMock(
                    returncode=0,
                    stdout=f"persistent-agent{SEP}$0{SEP}1234567890\n",
                    stderr=""
                )
        
        # Call list_agents multiple times
        for i in range(3):
            with patch('waggle.server.subprocess.run', side_effect=mock_tmux_run):
                with patch('waggle.server.get_db_path', return_value=str(db_path)):
                    result = await list_agents(
                        ctx=mock_ctx
                    )
            
            # Verify state is consistent across all calls
            assert result["status"] == "success"
            assert len(result["agents"]) == 1
            assert result["agents"][0]["name"] == "persistent-agent"
            assert result["agents"][0]["status"] == "processing data"
    

