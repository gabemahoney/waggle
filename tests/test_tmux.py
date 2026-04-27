"""Unit tests for waggle.tmux module — libtmux wrappers."""

from unittest.mock import patch, MagicMock, PropertyMock

import pytest

from libtmux.exc import LibTmuxException

from waggle.tmux import (
    get_sessions,
    is_llm_running,
    get_sessions_async,
    _kill_session_sync,
    kill_session,
    _check_llm_running_sync,
    check_llm_running,
    _capture_pane_sync,
    capture_pane,
    _create_session_sync,
    create_session,
    _launch_agent_in_pane_sync,
    launch_agent_in_pane,
    clone_or_update_repo,
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


class TestIsLlmRunning:
    """Tests for is_llm_running() — LLM detection via pane_current_command."""

    def test_detects_claude(self):
        """Verify 'claude' is detected as LLM."""
        pane = MagicMock()
        pane.pane_current_command = "claude"
        assert is_llm_running(pane) is True

    def test_detects_claude_case_insensitive(self):
        """Verify 'Claude' (capitalized) is detected as LLM."""
        pane = MagicMock()
        pane.pane_current_command = "Claude"
        assert is_llm_running(pane) is True

    def test_rejects_opencode(self):
        """Verify 'opencode' is NOT detected as LLM in v2."""
        pane = MagicMock()
        pane.pane_current_command = "opencode"
        assert is_llm_running(pane) is False

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


class TestCapturePaneSync:
    """Tests for _capture_pane_sync() — sync pane capture via libtmux."""

    @patch("waggle.tmux.libtmux.Server")
    def test_captures_active_pane_when_no_pane_id(self, mock_server_cls):
        """Verify captures active pane content when pane_id is None."""
        mock_server = MagicMock()
        mock_session = MagicMock()
        mock_pane = MagicMock()
        mock_pane.capture_pane.return_value = ["line1", "line2"]
        mock_session.active_window.active_pane = mock_pane
        mock_server.sessions.get.return_value = mock_session
        mock_server_cls.return_value = mock_server

        result = _capture_pane_sync("$0", None, 50)

        assert result == {"status": "success", "content": "line1\nline2"}

    @patch("waggle.tmux.libtmux.Server")
    def test_captures_specific_pane_when_pane_id_given(self, mock_server_cls):
        """Verify captures specific pane when pane_id is provided."""
        mock_server = MagicMock()
        mock_session = MagicMock()
        mock_pane = MagicMock()
        mock_pane.session_id = "$0"
        mock_pane.capture_pane.return_value = ["output"]
        mock_server.sessions.get.return_value = mock_session
        mock_server.panes.get.return_value = mock_pane
        mock_server_cls.return_value = mock_server

        result = _capture_pane_sync("$0", "%5", 50)

        mock_server.panes.get.assert_called_once_with(pane_id="%5")
        assert result == {"status": "success", "content": "output"}

    @patch("waggle.tmux.libtmux.Server")
    def test_pane_not_in_session_returns_error(self, mock_server_cls):
        """Verify returns error when pane does not belong to session."""
        mock_server = MagicMock()
        mock_session = MagicMock()
        mock_pane = MagicMock()
        mock_pane.session_id = "$99"
        mock_server.sessions.get.return_value = mock_session
        mock_server.panes.get.return_value = mock_pane
        mock_server_cls.return_value = mock_server

        result = _capture_pane_sync("$0", "%5", 50)

        assert result["status"] == "error"
        assert "does not belong" in result["message"]

    @patch("waggle.tmux.libtmux.Server")
    def test_session_not_found_returns_error(self, mock_server_cls):
        """Verify returns error when session lookup raises Exception."""
        mock_server = MagicMock()
        mock_server.sessions.get.side_effect = Exception("session not found")
        mock_server_cls.return_value = mock_server

        result = _capture_pane_sync("$99", None, 50)

        assert result["status"] == "error"
        assert "session not found" in result["message"]

    @patch("waggle.tmux.libtmux.Server")
    def test_libtmux_exception_returns_error(self, mock_server_cls):
        """Verify returns error on LibTmuxException."""
        mock_server = MagicMock()
        mock_server.sessions.get.side_effect = LibTmuxException("tmux error")
        mock_server_cls.return_value = mock_server

        result = _capture_pane_sync("$0", None, 50)

        assert result["status"] == "error"
        assert "tmux error" in result["message"]

    @patch("waggle.tmux.libtmux.Server")
    def test_empty_pane_returns_empty_content(self, mock_server_cls):
        """Verify returns empty content when pane has no output."""
        mock_server = MagicMock()
        mock_session = MagicMock()
        mock_pane = MagicMock()
        mock_pane.capture_pane.return_value = []
        mock_session.active_window.active_pane = mock_pane
        mock_server.sessions.get.return_value = mock_session
        mock_server_cls.return_value = mock_server

        result = _capture_pane_sync("$0", None, 50)

        assert result == {"status": "success", "content": ""}

    @patch("waggle.tmux.libtmux.Server")
    def test_scrollback_passed_to_capture_pane(self, mock_server_cls):
        """Verify default scrollback=50 is passed as start=-50."""
        mock_server = MagicMock()
        mock_session = MagicMock()
        mock_pane = MagicMock()
        mock_pane.capture_pane.return_value = []
        mock_session.active_window.active_pane = mock_pane
        mock_server.sessions.get.return_value = mock_session
        mock_server_cls.return_value = mock_server

        _capture_pane_sync("$0", None, 50)

        mock_pane.capture_pane.assert_called_once_with(start=-50)

    @patch("waggle.tmux.libtmux.Server")
    def test_custom_scrollback_passed(self, mock_server_cls):
        """Verify custom scrollback=100 is passed as start=-100."""
        mock_server = MagicMock()
        mock_session = MagicMock()
        mock_pane = MagicMock()
        mock_pane.capture_pane.return_value = []
        mock_session.active_window.active_pane = mock_pane
        mock_server.sessions.get.return_value = mock_session
        mock_server_cls.return_value = mock_server

        _capture_pane_sync("$0", None, 100)

        mock_pane.capture_pane.assert_called_once_with(start=-100)


class TestCapturePaneAsync:
    """Tests for capture_pane() — async wrapper delegating to _capture_pane_sync."""

    @pytest.mark.asyncio
    @patch("waggle.tmux._capture_pane_sync")
    async def test_delegates_to_sync(self, mock_sync):
        """Verify capture_pane delegates to _capture_pane_sync with defaults."""
        mock_sync.return_value = {"status": "success", "content": "hello"}

        result = await capture_pane("$0")

        mock_sync.assert_called_once_with("$0", None, 50)
        assert result == {"status": "success", "content": "hello"}

    @pytest.mark.asyncio
    @patch("waggle.tmux._capture_pane_sync")
    async def test_passes_pane_id_and_scrollback(self, mock_sync):
        """Verify capture_pane passes pane_id and scrollback to sync."""
        mock_sync.return_value = {"status": "success", "content": "data"}

        result = await capture_pane("$0", pane_id="%5", scrollback=100)

        mock_sync.assert_called_once_with("$0", "%5", 100)
        assert result == {"status": "success", "content": "data"}


class TestCreateSessionSync:
    """Tests for _create_session_sync() — new tmux session creation with WAGGLE_WORKER_ID."""

    @patch("waggle.tmux.libtmux.Server")
    def test_creates_session_returns_ids(self, mock_server_cls):
        """Verify new session creation returns session_id, name, created, and worker_id."""
        mock_server = MagicMock()
        mock_session = MagicMock()
        mock_session.session_id = "$5"
        mock_session.session_name = "my-agent"
        mock_session.session_created = "1700000000"
        mock_server.new_session.return_value = mock_session
        mock_server_cls.return_value = mock_server

        result = _create_session_sync("my-agent", "/home/user/repo", "worker-uuid-123")

        assert result["status"] == "success"
        assert result["session_id"] == "$5"
        assert result["session_name"] == "my-agent"
        assert result["session_created"] == "1700000000"
        assert result["worker_id"] == "worker-uuid-123"
        mock_server.new_session.assert_called_once_with(
            session_name="my-agent",
            start_directory="/home/user/repo",
            attach=False,
            environment={"VIRTUAL_ENV": "", "VIRTUAL_ENV_PROMPT": ""},
        )
        mock_session.set_environment.assert_called_once_with("WAGGLE_WORKER_ID", "worker-uuid-123")

    @patch("waggle.tmux.libtmux.Server")
    def test_libtmux_exception_caught(self, mock_server_cls):
        """Verify LibTmuxException from new_session is caught and returned as error dict."""
        mock_server = MagicMock()
        mock_server.new_session.side_effect = LibTmuxException("session already exists")
        mock_server_cls.return_value = mock_server

        result = _create_session_sync("my-agent", "/repo", "worker-uuid")

        assert result["status"] == "error"
        assert result["message"]

    @patch("waggle.tmux.libtmux.Server")
    def test_generic_exception_caught(self, mock_server_cls):
        """Verify generic Exception is caught and returned as error dict."""
        mock_server_cls.side_effect = Exception("tmux not running")

        result = _create_session_sync("my-agent", "/repo", "worker-uuid")

        assert result["status"] == "error"
        assert "tmux not running" in result["message"]


class TestCreateSessionAsync:
    """Tests for create_session() — async wrapper."""

    @pytest.mark.asyncio
    @patch("waggle.tmux._create_session_sync")
    async def test_delegates_to_sync(self, mock_sync):
        """Verify create_session delegates to _create_session_sync with worker_id."""
        mock_sync.return_value = {
            "status": "success",
            "session_id": "$5",
            "session_name": "my-agent",
            "session_created": "1700000000",
            "worker_id": "worker-uuid-123",
        }

        result = await create_session("my-agent", "/repo", "worker-uuid-123")

        mock_sync.assert_called_once_with("my-agent", "/repo", "worker-uuid-123")
        assert result["status"] == "success"
        assert result["worker_id"] == "worker-uuid-123"


class TestLaunchAgentInPaneSync:
    """Tests for _launch_agent_in_pane_sync() — sending claude launch command to pane.

    v2 signature: (session_id, model, settings) — always launches claude.
    """

    @patch("waggle.tmux.libtmux.Server")
    def test_sends_claude_with_model(self, mock_server_cls):
        """Verify 'claude --model sonnet' is sent to the active pane."""
        mock_server = MagicMock()
        mock_session = MagicMock()
        mock_pane = MagicMock()
        mock_session.active_window.active_pane = mock_pane
        mock_server.sessions.get.return_value = mock_session
        mock_server_cls.return_value = mock_server

        result = _launch_agent_in_pane_sync("$1", "sonnet", None)

        assert result == {"status": "success"}
        mock_pane.send_keys.assert_called_once_with("claude --model sonnet", enter=True)

    @patch("waggle.tmux.libtmux.Server")
    def test_model_lowercased(self, mock_server_cls):
        """Verify model name is lowercased in the command."""
        mock_server = MagicMock()
        mock_session = MagicMock()
        mock_pane = MagicMock()
        mock_session.active_window.active_pane = mock_pane
        mock_server.sessions.get.return_value = mock_session
        mock_server_cls.return_value = mock_server

        result = _launch_agent_in_pane_sync("$1", "Opus", None)

        assert result == {"status": "success"}
        mock_pane.send_keys.assert_called_once_with("claude --model opus", enter=True)

    @patch("waggle.tmux.libtmux.Server")
    def test_appends_settings_to_command(self, mock_server_cls):
        """Verify extra settings flags are appended to the claude command."""
        mock_server = MagicMock()
        mock_session = MagicMock()
        mock_pane = MagicMock()
        mock_session.active_window.active_pane = mock_pane
        mock_server.sessions.get.return_value = mock_session
        mock_server_cls.return_value = mock_server

        result = _launch_agent_in_pane_sync("$1", "sonnet", "--dangerously-skip-permissions")

        assert result == {"status": "success"}
        mock_pane.send_keys.assert_called_once_with(
            "claude --model sonnet --dangerously-skip-permissions", enter=True
        )

    @patch("waggle.tmux.libtmux.Server")
    def test_rejects_shell_injection_in_settings(self, mock_server_cls):
        """Verify settings with shell metacharacters are rejected."""
        result = _launch_agent_in_pane_sync("$1", "sonnet", "; rm -rf /")

        assert result["status"] == "error"
        assert "invalid characters" in result["message"]

    @patch("waggle.tmux.libtmux.Server")
    def test_libtmux_exception_caught(self, mock_server_cls):
        """Verify LibTmuxException is caught and returned as error dict."""
        mock_server = MagicMock()
        mock_server.sessions.get.side_effect = LibTmuxException("no session")
        mock_server_cls.return_value = mock_server

        result = _launch_agent_in_pane_sync("$1", "sonnet", None)

        assert result["status"] == "error"
        assert result["message"]


class TestLaunchAgentInPaneAsync:
    """Tests for launch_agent_in_pane() — async wrapper."""

    @pytest.mark.asyncio
    @patch("waggle.tmux._launch_agent_in_pane_sync")
    async def test_delegates_to_sync(self, mock_sync):
        """Verify launch_agent_in_pane delegates to _launch_agent_in_pane_sync."""
        mock_sync.return_value = {"status": "success"}

        result = await launch_agent_in_pane("$1", "sonnet", "--no-interactive")

        mock_sync.assert_called_once_with("$1", "sonnet", "--no-interactive", None)
        assert result == {"status": "success"}

    @pytest.mark.asyncio
    @patch("waggle.tmux._launch_agent_in_pane_sync")
    async def test_settings_defaults_to_none(self, mock_sync):
        """Verify settings defaults to None when not provided."""
        mock_sync.return_value = {"status": "success"}

        result = await launch_agent_in_pane("$1", "haiku")

        mock_sync.assert_called_once_with("$1", "haiku", None, None)
        assert result == {"status": "success"}
