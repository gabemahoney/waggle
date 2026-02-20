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
    _kill_session_sync,
    kill_session,
    _validate_session_name_id_sync,
    validate_session_name_id,
    _check_llm_running_sync,
    check_llm_running,
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


class TestKillSessionSync:
    """Tests for _kill_session_sync() — sync dict-return kill via libtmux."""

    @patch("waggle.tmux.libtmux.Server")
    def test_success(self, mock_server_cls):
        """Verify returns {"status": "success"} when session is killed."""
        mock_server = MagicMock()
        mock_session = MagicMock()
        mock_server.sessions.get.return_value = mock_session
        mock_server_cls.return_value = mock_server

        result = _kill_session_sync("$3")

        mock_server.sessions.get.assert_called_once_with(session_id="$3")
        mock_session.kill.assert_called_once()
        assert result == {"status": "success"}

    @patch("waggle.tmux.libtmux.Server")
    def test_session_not_found_returns_error(self, mock_server_cls):
        """Verify returns error dict when QueryList.get() raises Exception."""
        mock_server = MagicMock()
        mock_server.sessions.get.side_effect = Exception("session not found")
        mock_server_cls.return_value = mock_server

        result = _kill_session_sync("$99")

        assert result["status"] == "error"
        assert "session not found" in result["message"]

    @patch("waggle.tmux.libtmux.Server")
    def test_kill_failure_returns_error(self, mock_server_cls):
        """Verify returns error dict when session.kill() raises LibTmuxException."""
        mock_server = MagicMock()
        mock_session = MagicMock()
        mock_session.kill.side_effect = LibTmuxException("kill failed")
        mock_server.sessions.get.return_value = mock_session
        mock_server_cls.return_value = mock_server

        result = _kill_session_sync("$3")

        assert result["status"] == "error"
        assert "kill failed" in result["message"]

    @patch("waggle.tmux.libtmux.Server")
    def test_tmux_unavailable_returns_error(self, mock_server_cls):
        """Verify returns error dict when tmux server is unavailable."""
        mock_server_cls.side_effect = Exception("no server running")

        result = _kill_session_sync("$3")

        assert result["status"] == "error"
        assert "no server running" in result["message"]


class TestKillSessionAsync:
    """Tests for kill_session() — async wrapper delegating to _kill_session_sync."""

    @pytest.mark.asyncio
    @patch("waggle.tmux._kill_session_sync")
    async def test_delegates_to_sync(self, mock_sync):
        """Verify kill_session delegates to _kill_session_sync and returns its result."""
        mock_sync.return_value = {"status": "success"}

        result = await kill_session("$3")

        mock_sync.assert_called_once_with("$3")
        assert result == {"status": "success"}

    @pytest.mark.asyncio
    @patch("waggle.tmux._kill_session_sync")
    async def test_returns_error_from_sync(self, mock_sync):
        """Verify kill_session passes through error dict from _kill_session_sync."""
        mock_sync.return_value = {"status": "error", "message": "kill failed"}

        result = await kill_session("$99")

        assert result == {"status": "error", "message": "kill failed"}


class TestValidateSessionNameIdSync:
    """Tests for _validate_session_name_id_sync() — sync dict-return name validation."""

    @patch("waggle.tmux.libtmux.Server")
    def test_success(self, mock_server_cls):
        """Verify returns {"status": "success"} when session is found and name matches."""
        mock_server = MagicMock()
        mock_session = MagicMock()
        mock_session.session_name = "agent1"
        mock_server.sessions.get.return_value = mock_session
        mock_server_cls.return_value = mock_server

        result = _validate_session_name_id_sync("$0", "agent1")

        assert result == {"status": "success"}

    @patch("waggle.tmux.libtmux.Server")
    def test_name_mismatch_returns_error(self, mock_server_cls):
        """Verify returns error dict with mismatch message when names differ."""
        mock_server = MagicMock()
        mock_session = MagicMock()
        mock_session.session_name = "other-agent"
        mock_server.sessions.get.return_value = mock_session
        mock_server_cls.return_value = mock_server

        result = _validate_session_name_id_sync("$0", "agent1")

        assert result["status"] == "error"
        assert "mismatch" in result["message"].lower()
        assert "agent1" in result["message"]
        assert "other-agent" in result["message"]

    @patch("waggle.tmux.libtmux.Server")
    def test_session_not_found_libtmux_exception(self, mock_server_cls):
        """Verify returns error dict on LibTmuxException."""
        mock_server = MagicMock()
        mock_server.sessions.get.side_effect = LibTmuxException("no session")
        mock_server_cls.return_value = mock_server

        result = _validate_session_name_id_sync("$99", "agent1")

        assert result["status"] == "error"
        assert result["message"]

    @patch("waggle.tmux.libtmux.Server")
    def test_session_not_found_generic_exception(self, mock_server_cls):
        """Verify returns error dict on generic Exception."""
        mock_server = MagicMock()
        mock_server.sessions.get.side_effect = Exception("QueryList error")
        mock_server_cls.return_value = mock_server

        result = _validate_session_name_id_sync("$99", "agent1")

        assert result["status"] == "error"
        assert result["message"]


class TestValidateSessionNameIdAsync:
    """Tests for validate_session_name_id() — async wrapper."""

    @pytest.mark.asyncio
    @patch("waggle.tmux._validate_session_name_id_sync")
    async def test_delegates_to_sync(self, mock_sync):
        """Verify validate_session_name_id delegates to _validate_session_name_id_sync."""
        mock_sync.return_value = {"status": "success"}

        result = await validate_session_name_id("$0", "agent1")

        mock_sync.assert_called_once_with("$0", "agent1")
        assert result == {"status": "success"}


class TestCheckLlmRunningSync:
    """Tests for _check_llm_running_sync() — sync LLM detection via active pane."""

    @patch("waggle.tmux.libtmux.Server")
    def test_returns_true_when_llm_running(self, mock_server_cls):
        """Verify returns True when active pane is running claude."""
        mock_server = MagicMock()
        mock_session = MagicMock()
        mock_pane = MagicMock()
        mock_pane.pane_current_command = "claude"
        mock_session.active_window.active_pane = mock_pane
        mock_server.sessions.get.return_value = mock_session
        mock_server_cls.return_value = mock_server

        result = _check_llm_running_sync("$0")

        assert result is True

    @patch("waggle.tmux.libtmux.Server")
    def test_returns_false_when_not_llm(self, mock_server_cls):
        """Verify returns False when active pane is running zsh."""
        mock_server = MagicMock()
        mock_session = MagicMock()
        mock_pane = MagicMock()
        mock_pane.pane_current_command = "zsh"
        mock_session.active_window.active_pane = mock_pane
        mock_server.sessions.get.return_value = mock_session
        mock_server_cls.return_value = mock_server

        result = _check_llm_running_sync("$0")

        assert result is False

    @patch("waggle.tmux.libtmux.Server")
    def test_returns_false_on_exception(self, mock_server_cls):
        """Verify returns False when session lookup raises."""
        mock_server = MagicMock()
        mock_server.sessions.get.side_effect = Exception("no session")
        mock_server_cls.return_value = mock_server

        result = _check_llm_running_sync("$99")

        assert result is False


class TestCheckLlmRunningAsync:
    """Tests for check_llm_running() — async wrapper."""

    @pytest.mark.asyncio
    @patch("waggle.tmux._check_llm_running_sync")
    async def test_delegates_to_sync(self, mock_sync):
        """Verify check_llm_running delegates to _check_llm_running_sync."""
        mock_sync.return_value = True

        result = await check_llm_running("$0")

        mock_sync.assert_called_once_with("$0")
        assert result is True
