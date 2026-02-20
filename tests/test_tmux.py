"""Unit tests for waggle.tmux module — libtmux wrappers."""

from unittest.mock import patch, MagicMock, PropertyMock

import pytest

from libtmux.exc import LibTmuxException

from waggle.tmux import (
    get_sessions,
    get_active_session_keys,
    is_llm_running,
    get_sessions_async,
    get_active_session_keys_async,
)


def _make_mock_session(name, session_id, created, path):
    """Helper to build a mock libtmux Session with required attributes."""
    s = MagicMock()
    s.session_name = name
    s.session_id = session_id
    s.session_created = created
    s.session_path = path
    return s


class TestGetSessions:
    """Tests for get_sessions() — session enumeration via libtmux."""

    @patch("waggle.tmux.libtmux.Server")
    def test_returns_session_data(self, mock_server_cls):
        """Verify get_sessions returns list of dicts with correct keys/values."""
        mock_server = MagicMock()
        mock_server.sessions = [
            _make_mock_session("agent1", "$0", "1111111111", "/path/one"),
            _make_mock_session("agent2", "$1", "2222222222", "/path/two"),
        ]
        mock_server_cls.return_value = mock_server

        result = get_sessions()

        assert len(result) == 2
        assert result[0] == {
            "session_name": "agent1",
            "session_id": "$0",
            "session_created": "1111111111",
            "session_path": "/path/one",
        }
        assert result[1] == {
            "session_name": "agent2",
            "session_id": "$1",
            "session_created": "2222222222",
            "session_path": "/path/two",
        }

    @patch("waggle.tmux.libtmux.Server")
    def test_returns_empty_list_when_no_sessions(self, mock_server_cls):
        """Verify get_sessions returns [] when tmux has no sessions."""
        mock_server = MagicMock()
        mock_server.sessions = []
        mock_server_cls.return_value = mock_server

        result = get_sessions()

        assert result == []

    @patch("waggle.tmux.libtmux.Server")
    def test_returns_empty_list_when_tmux_unavailable(self, mock_server_cls):
        """Verify get_sessions returns [] when tmux server is not running."""
        mock_server_cls.side_effect = Exception("no server running")

        result = get_sessions()

        assert result == []

    @patch("waggle.tmux.libtmux.Server")
    def test_returns_empty_list_on_libtmux_exception(self, mock_server_cls):
        """Verify get_sessions returns [] on LibTmuxException."""
        mock_server_cls.side_effect = LibTmuxException()

        result = get_sessions()

        assert result == []


class TestGetActiveSessionKeys:
    """Tests for get_active_session_keys() — composite key generation."""

    @patch("waggle.tmux.get_sessions")
    def test_returns_composite_keys(self, mock_get_sessions):
        """Verify composite keys follow '{name}+{id}+{created}' format."""
        mock_get_sessions.return_value = [
            {"session_name": "agent1", "session_id": "$0", "session_created": "111", "session_path": "/p1"},
            {"session_name": "agent2", "session_id": "$1", "session_created": "222", "session_path": "/p2"},
        ]

        result = get_active_session_keys()

        assert result == {"agent1+$0+111", "agent2+$1+222"}

    @patch("waggle.tmux.get_sessions")
    def test_returns_empty_set_when_no_sessions(self, mock_get_sessions):
        """Verify returns empty set when no sessions exist."""
        mock_get_sessions.return_value = []

        result = get_active_session_keys()

        assert result == set()

    @patch("waggle.tmux.get_sessions")
    def test_returns_empty_set_on_error(self, mock_get_sessions):
        """Verify returns empty set when get_sessions raises."""
        mock_get_sessions.side_effect = Exception("unexpected error")

        result = get_active_session_keys()

        assert result == set()


class TestIsLlmRunning:
    """Tests for is_llm_running() — LLM detection via pane_current_command."""

    def test_detects_claude(self):
        """Verify 'claude' is detected as LLM."""
        pane = MagicMock()
        pane.pane_current_command = "claude"
        assert is_llm_running(pane) is True

    def test_detects_opencode(self):
        """Verify 'opencode' is detected as LLM."""
        pane = MagicMock()
        pane.pane_current_command = "opencode"
        assert is_llm_running(pane) is True

    def test_detects_claude_case_insensitive(self):
        """Verify 'Claude' (capitalized) is detected as LLM."""
        pane = MagicMock()
        pane.pane_current_command = "Claude"
        assert is_llm_running(pane) is True

    def test_detects_opencode_case_insensitive(self):
        """Verify 'OpenCode' (mixed case) is detected as LLM."""
        pane = MagicMock()
        pane.pane_current_command = "OpenCode"
        assert is_llm_running(pane) is True

    def test_returns_false_for_zsh(self):
        """Verify 'zsh' is NOT detected as LLM."""
        pane = MagicMock()
        pane.pane_current_command = "zsh"
        assert is_llm_running(pane) is False

    def test_returns_false_for_bash(self):
        """Verify 'bash' is NOT detected as LLM."""
        pane = MagicMock()
        pane.pane_current_command = "bash"
        assert is_llm_running(pane) is False

    def test_returns_false_for_node(self):
        """Verify 'node' is NOT detected as LLM."""
        pane = MagicMock()
        pane.pane_current_command = "node"
        assert is_llm_running(pane) is False

    def test_returns_false_for_none_command(self):
        """Verify None pane_current_command returns False."""
        pane = MagicMock()
        pane.pane_current_command = None
        assert is_llm_running(pane) is False

    def test_returns_false_on_error(self):
        """Verify returns False when accessing pane_current_command raises."""
        pane = MagicMock()
        type(pane).pane_current_command = PropertyMock(side_effect=Exception("pane error"))
        assert is_llm_running(pane) is False


class TestAsyncWrappers:
    """Tests for async wrappers — verify they delegate to sync functions."""

    @pytest.mark.asyncio
    @patch("waggle.tmux.get_sessions")
    async def test_get_sessions_async(self, mock_get_sessions):
        """Verify get_sessions_async delegates to get_sessions."""
        expected = [{"session_name": "a", "session_id": "$0", "session_created": "1", "session_path": "/p"}]
        mock_get_sessions.return_value = expected

        result = await get_sessions_async()

        mock_get_sessions.assert_called_once()
        assert result == expected

    @pytest.mark.asyncio
    @patch("waggle.tmux.get_active_session_keys")
    async def test_get_active_session_keys_async(self, mock_get_keys):
        """Verify get_active_session_keys_async delegates to get_active_session_keys."""
        expected = {"agent+$0+111"}
        mock_get_keys.return_value = expected

        result = await get_active_session_keys_async()

        mock_get_keys.assert_called_once()
        assert result == expected
