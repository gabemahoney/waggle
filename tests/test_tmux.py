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
    _capture_pane_sync,
    capture_pane,
    _validate_pane_id_sync,
    validate_pane_id,
    _send_keys_to_pane_sync,
    send_keys_to_pane,
    _clear_pane_input_sync,
    clear_pane_input,
    _create_session_sync,
    create_session,
    _launch_agent_in_pane_sync,
    launch_agent_in_pane,
    _resolve_session_sync,
    resolve_session,
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


class TestValidatePaneIdSync:
    """Tests for _validate_pane_id_sync() — sync pane-session membership check."""

    @patch("waggle.tmux.libtmux.Server")
    def test_success(self, mock_server_cls):
        """Verify returns {"status": "success"} when pane belongs to session."""
        mock_server = MagicMock()
        mock_session = MagicMock()
        mock_pane = MagicMock()
        mock_pane.session_id = "$0"
        mock_server.sessions.get.return_value = mock_session
        mock_server.panes.get.return_value = mock_pane
        mock_server_cls.return_value = mock_server

        result = _validate_pane_id_sync("$0", "%3")

        assert result == {"status": "success"}

    @patch("waggle.tmux.libtmux.Server")
    def test_invalid_pane_id_returns_error(self, mock_server_cls):
        """Verify returns error dict when pane lookup raises Exception."""
        mock_server = MagicMock()
        mock_session = MagicMock()
        mock_server.sessions.get.return_value = mock_session
        mock_server.panes.get.side_effect = Exception("pane not found")
        mock_server_cls.return_value = mock_server

        result = _validate_pane_id_sync("$0", "%99")

        assert result["status"] == "error"
        assert result["message"]

    @patch("waggle.tmux.libtmux.Server")
    def test_pane_from_different_session_returns_error(self, mock_server_cls):
        """Verify returns descriptive error when pane belongs to different session."""
        mock_server = MagicMock()
        mock_session = MagicMock()
        mock_pane = MagicMock()
        mock_pane.session_id = "$99"
        mock_server.sessions.get.return_value = mock_session
        mock_server.panes.get.return_value = mock_pane
        mock_server_cls.return_value = mock_server

        result = _validate_pane_id_sync("$0", "%3")

        assert result["status"] == "error"
        assert "%3" in result["message"]
        assert "$0" in result["message"]

    @patch("waggle.tmux.libtmux.Server")
    def test_libtmux_exception_caught_returns_error(self, mock_server_cls):
        """Verify LibTmuxException is caught and returned as error dict."""
        mock_server = MagicMock()
        mock_server.sessions.get.side_effect = LibTmuxException("no session")
        mock_server_cls.return_value = mock_server

        result = _validate_pane_id_sync("$0", "%3")

        assert result["status"] == "error"
        assert result["message"]

    @patch("waggle.tmux.libtmux.Server")
    def test_session_validation_called_with_correct_id(self, mock_server_cls):
        """Verify sessions.get is called with the correct session_id."""
        mock_server = MagicMock()
        mock_session = MagicMock()
        mock_pane = MagicMock()
        mock_pane.session_id = "$2"
        mock_server.sessions.get.return_value = mock_session
        mock_server.panes.get.return_value = mock_pane
        mock_server_cls.return_value = mock_server

        _validate_pane_id_sync("$2", "%7")

        mock_server.sessions.get.assert_called_once_with(session_id="$2")
        mock_server.panes.get.assert_called_once_with(pane_id="%7")


class TestValidatePaneIdAsync:
    """Tests for validate_pane_id() — async wrapper delegating to _validate_pane_id_sync."""

    @pytest.mark.asyncio
    @patch("waggle.tmux._validate_pane_id_sync")
    async def test_delegates_to_sync(self, mock_sync):
        """Verify validate_pane_id delegates to _validate_pane_id_sync."""
        mock_sync.return_value = {"status": "success"}

        result = await validate_pane_id("$0", "%3")

        mock_sync.assert_called_once_with("$0", "%3")
        assert result == {"status": "success"}

    @pytest.mark.asyncio
    @patch("waggle.tmux._validate_pane_id_sync")
    async def test_returns_error_from_sync(self, mock_sync):
        """Verify validate_pane_id passes through error dict from _validate_pane_id_sync."""
        mock_sync.return_value = {"status": "error", "message": "Pane '%3' does not belong to session '$0'"}

        result = await validate_pane_id("$0", "%3")

        assert result == {"status": "error", "message": "Pane '%3' does not belong to session '$0'"}


class TestSendKeysToPaneSync:
    """Tests for _send_keys_to_pane_sync() — send text to a pane."""

    @patch("waggle.tmux.libtmux.Server")
    def test_sends_text_with_enter_to_active_pane(self, mock_server_cls):
        """Verify send_keys called with text and enter=True on active pane."""
        mock_server = MagicMock()
        mock_session = MagicMock()
        mock_pane = MagicMock()
        mock_session.active_window.active_pane = mock_pane
        mock_server.sessions.get.return_value = mock_session
        mock_server_cls.return_value = mock_server

        result = _send_keys_to_pane_sync("$0", "hello", None, True)

        assert result == {"status": "success"}
        mock_pane.send_keys.assert_called_once_with("hello", enter=True)

    @patch("waggle.tmux.libtmux.Server")
    def test_sends_text_without_enter(self, mock_server_cls):
        """Verify send_keys called with enter=False when enter param is False."""
        mock_server = MagicMock()
        mock_session = MagicMock()
        mock_pane = MagicMock()
        mock_session.active_window.active_pane = mock_pane
        mock_server.sessions.get.return_value = mock_session
        mock_server_cls.return_value = mock_server

        result = _send_keys_to_pane_sync("$0", "partial", None, False)

        assert result == {"status": "success"}
        mock_pane.send_keys.assert_called_once_with("partial", enter=False)

    @patch("waggle.tmux.libtmux.Server")
    def test_targets_specific_pane_id(self, mock_server_cls):
        """Verify specific pane_id is resolved via server.panes.get."""
        mock_server = MagicMock()
        mock_session = MagicMock()
        mock_pane = MagicMock()
        mock_pane.session_id = "$0"
        mock_server.sessions.get.return_value = mock_session
        mock_server.panes.get.return_value = mock_pane
        mock_server_cls.return_value = mock_server

        result = _send_keys_to_pane_sync("$0", "cmd", "%3", True)

        assert result == {"status": "success"}
        mock_server.panes.get.assert_called_once_with(pane_id="%3")
        mock_pane.send_keys.assert_called_once_with("cmd", enter=True)

    @patch("waggle.tmux.libtmux.Server")
    def test_pane_from_wrong_session_returns_error(self, mock_server_cls):
        """Verify error when pane_id belongs to a different session."""
        mock_server = MagicMock()
        mock_session = MagicMock()
        mock_pane = MagicMock()
        mock_pane.session_id = "$99"
        mock_server.sessions.get.return_value = mock_session
        mock_server.panes.get.return_value = mock_pane
        mock_server_cls.return_value = mock_server

        result = _send_keys_to_pane_sync("$0", "cmd", "%3", True)

        assert result["status"] == "error"
        assert "%3" in result["message"]
        assert "$0" in result["message"]

    @patch("waggle.tmux.libtmux.Server")
    def test_libtmux_exception_caught(self, mock_server_cls):
        """Verify LibTmuxException is caught and returned as error dict."""
        mock_server = MagicMock()
        mock_server.sessions.get.side_effect = LibTmuxException("session not found")
        mock_server_cls.return_value = mock_server

        result = _send_keys_to_pane_sync("$0", "cmd", None, True)

        assert result["status"] == "error"
        assert result["message"]

    @patch("waggle.tmux.libtmux.Server")
    def test_generic_exception_caught(self, mock_server_cls):
        """Verify generic Exception is caught and returned as error dict."""
        mock_server = MagicMock()
        mock_session = MagicMock()
        mock_pane = MagicMock()
        mock_session.active_window.active_pane = mock_pane
        mock_pane.send_keys.side_effect = Exception("unexpected error")
        mock_server.sessions.get.return_value = mock_session
        mock_server_cls.return_value = mock_server

        result = _send_keys_to_pane_sync("$0", "cmd", None, True)

        assert result["status"] == "error"
        assert "unexpected error" in result["message"]


class TestSendKeysToPaneAsync:
    """Tests for send_keys_to_pane() — async wrapper."""

    @pytest.mark.asyncio
    @patch("waggle.tmux._send_keys_to_pane_sync")
    async def test_delegates_to_sync(self, mock_sync):
        """Verify send_keys_to_pane delegates to _send_keys_to_pane_sync."""
        mock_sync.return_value = {"status": "success"}

        result = await send_keys_to_pane("$0", "hello")

        mock_sync.assert_called_once_with("$0", "hello", None, True)
        assert result == {"status": "success"}

    @pytest.mark.asyncio
    @patch("waggle.tmux._send_keys_to_pane_sync")
    async def test_passes_pane_id_and_enter_false(self, mock_sync):
        """Verify optional pane_id and enter=False are forwarded."""
        mock_sync.return_value = {"status": "success"}

        result = await send_keys_to_pane("$0", "cmd", pane_id="%5", enter=False)

        mock_sync.assert_called_once_with("$0", "cmd", "%5", False)
        assert result == {"status": "success"}

    @pytest.mark.asyncio
    @patch("waggle.tmux._send_keys_to_pane_sync")
    async def test_returns_error_from_sync(self, mock_sync):
        """Verify error dict is passed through from sync function."""
        mock_sync.return_value = {"status": "error", "message": "session not found"}

        result = await send_keys_to_pane("$0", "cmd")

        assert result == {"status": "error", "message": "session not found"}


class TestClearPaneInputSync:
    """Tests for _clear_pane_input_sync() — send Ctrl+C to clear partial input."""

    @patch("waggle.tmux.libtmux.Server")
    def test_sends_ctrl_c_to_active_pane(self, mock_server_cls):
        """Verify C-c sent without Enter to active pane."""
        mock_server = MagicMock()
        mock_session = MagicMock()
        mock_pane = MagicMock()
        mock_session.active_window.active_pane = mock_pane
        mock_server.sessions.get.return_value = mock_session
        mock_server_cls.return_value = mock_server

        result = _clear_pane_input_sync("$0", None)

        assert result == {"status": "success"}
        mock_pane.send_keys.assert_called_once_with("C-c", enter=False)

    @patch("waggle.tmux.libtmux.Server")
    def test_sends_ctrl_c_to_specific_pane(self, mock_server_cls):
        """Verify C-c is sent to the specific pane_id when provided."""
        mock_server = MagicMock()
        mock_session = MagicMock()
        mock_pane = MagicMock()
        mock_pane.session_id = "$0"
        mock_server.sessions.get.return_value = mock_session
        mock_server.panes.get.return_value = mock_pane
        mock_server_cls.return_value = mock_server

        result = _clear_pane_input_sync("$0", "%3")

        assert result == {"status": "success"}
        mock_server.panes.get.assert_called_once_with(pane_id="%3")
        mock_pane.send_keys.assert_called_once_with("C-c", enter=False)

    @patch("waggle.tmux.libtmux.Server")
    def test_pane_from_wrong_session_returns_error(self, mock_server_cls):
        """Verify error when pane_id belongs to a different session."""
        mock_server = MagicMock()
        mock_session = MagicMock()
        mock_pane = MagicMock()
        mock_pane.session_id = "$99"
        mock_server.sessions.get.return_value = mock_session
        mock_server.panes.get.return_value = mock_pane
        mock_server_cls.return_value = mock_server

        result = _clear_pane_input_sync("$0", "%3")

        assert result["status"] == "error"
        assert "%3" in result["message"]

    @patch("waggle.tmux.libtmux.Server")
    def test_libtmux_exception_caught(self, mock_server_cls):
        """Verify LibTmuxException is caught and returned as error dict."""
        mock_server = MagicMock()
        mock_server.sessions.get.side_effect = LibTmuxException("no session")
        mock_server_cls.return_value = mock_server

        result = _clear_pane_input_sync("$0", None)

        assert result["status"] == "error"
        assert result["message"]

    @patch("waggle.tmux.libtmux.Server")
    def test_generic_exception_caught(self, mock_server_cls):
        """Verify generic Exception is caught and returned as error dict."""
        mock_server = MagicMock()
        mock_session = MagicMock()
        mock_pane = MagicMock()
        mock_session.active_window.active_pane = mock_pane
        mock_pane.send_keys.side_effect = Exception("unexpected")
        mock_server.sessions.get.return_value = mock_session
        mock_server_cls.return_value = mock_server

        result = _clear_pane_input_sync("$0", None)

        assert result["status"] == "error"
        assert "unexpected" in result["message"]


class TestClearPaneInputAsync:
    """Tests for clear_pane_input() — async wrapper."""

    @pytest.mark.asyncio
    @patch("waggle.tmux._clear_pane_input_sync")
    async def test_delegates_to_sync(self, mock_sync):
        """Verify clear_pane_input delegates to _clear_pane_input_sync."""
        mock_sync.return_value = {"status": "success"}

        result = await clear_pane_input("$0")

        mock_sync.assert_called_once_with("$0", None)
        assert result == {"status": "success"}

    @pytest.mark.asyncio
    @patch("waggle.tmux._clear_pane_input_sync")
    async def test_passes_pane_id(self, mock_sync):
        """Verify optional pane_id is forwarded to sync function."""
        mock_sync.return_value = {"status": "success"}

        result = await clear_pane_input("$0", pane_id="%7")

        mock_sync.assert_called_once_with("$0", "%7")
        assert result == {"status": "success"}

    @pytest.mark.asyncio
    @patch("waggle.tmux._clear_pane_input_sync")
    async def test_returns_error_from_sync(self, mock_sync):
        """Verify error dict is passed through from sync function."""
        mock_sync.return_value = {"status": "error", "message": "no session"}

        result = await clear_pane_input("$0")

        assert result == {"status": "error", "message": "no session"}


class TestCreateSessionSync:
    """Tests for _create_session_sync() — new tmux session creation."""

    @patch("waggle.tmux.libtmux.Server")
    def test_creates_session_returns_ids(self, mock_server_cls):
        """Verify new session creation returns session_id, name, and created timestamp."""
        mock_server = MagicMock()
        mock_session = MagicMock()
        mock_session.session_id = "$5"
        mock_session.session_name = "my-agent"
        mock_session.session_created = "1700000000"
        mock_server.new_session.return_value = mock_session
        mock_server_cls.return_value = mock_server

        result = _create_session_sync("my-agent", "/home/user/repo")

        assert result["status"] == "success"
        assert result["session_id"] == "$5"
        assert result["session_name"] == "my-agent"
        assert result["session_created"] == "1700000000"
        mock_server.new_session.assert_called_once_with(
            session_name="my-agent",
            start_directory="/home/user/repo",
            attach=False,
            environment={"VIRTUAL_ENV": "", "VIRTUAL_ENV_PROMPT": ""},
        )

    @patch("waggle.tmux.libtmux.Server")
    def test_libtmux_exception_caught(self, mock_server_cls):
        """Verify LibTmuxException from new_session is caught and returned as error dict."""
        mock_server = MagicMock()
        mock_server.new_session.side_effect = LibTmuxException("session already exists")
        mock_server_cls.return_value = mock_server

        result = _create_session_sync("my-agent", "/repo")

        assert result["status"] == "error"
        assert result["message"]

    @patch("waggle.tmux.libtmux.Server")
    def test_generic_exception_caught(self, mock_server_cls):
        """Verify generic Exception is caught and returned as error dict."""
        mock_server_cls.side_effect = Exception("tmux not running")

        result = _create_session_sync("my-agent", "/repo")

        assert result["status"] == "error"
        assert "tmux not running" in result["message"]


class TestCreateSessionAsync:
    """Tests for create_session() — async wrapper."""

    @pytest.mark.asyncio
    @patch("waggle.tmux._create_session_sync")
    async def test_delegates_to_sync(self, mock_sync):
        """Verify create_session delegates to _create_session_sync."""
        mock_sync.return_value = {
            "status": "success",
            "session_id": "$5",
            "session_name": "my-agent",
            "session_created": "1700000000",
        }

        result = await create_session("my-agent", "/repo")

        mock_sync.assert_called_once_with("my-agent", "/repo")
        assert result["status"] == "success"


class TestLaunchAgentInPaneSync:
    """Tests for _launch_agent_in_pane_sync() — sending agent launch command to pane."""

    @patch("waggle.tmux.libtmux.Server")
    def test_sends_claude_command(self, mock_server_cls):
        """Verify 'claude' is sent to the active pane with Enter."""
        mock_server = MagicMock()
        mock_session = MagicMock()
        mock_pane = MagicMock()
        mock_session.active_window.active_pane = mock_pane
        mock_server.sessions.get.return_value = mock_session
        mock_server_cls.return_value = mock_server

        result = _launch_agent_in_pane_sync("$1", "claude", None, None)

        assert result == {"status": "success"}
        mock_pane.send_keys.assert_called_once_with("claude", enter=True)

    @patch("waggle.tmux.libtmux.Server")
    def test_sends_claude_with_model(self, mock_server_cls):
        """Verify model flag appended to claude command."""
        mock_server = MagicMock()
        mock_session = MagicMock()
        mock_pane = MagicMock()
        mock_session.active_window.active_pane = mock_pane
        mock_server.sessions.get.return_value = mock_session
        mock_server_cls.return_value = mock_server

        result = _launch_agent_in_pane_sync("$1", "claude", "sonnet", None)

        assert result == {"status": "success"}
        mock_pane.send_keys.assert_called_once_with("claude --model sonnet", enter=True)

    @patch("waggle.tmux.libtmux.Server")
    def test_sends_opencode_without_model(self, mock_server_cls):
        """Verify opencode is sent without model flag when model is None."""
        mock_server = MagicMock()
        mock_session = MagicMock()
        mock_pane = MagicMock()
        mock_session.active_window.active_pane = mock_pane
        mock_server.sessions.get.return_value = mock_session
        mock_server_cls.return_value = mock_server

        result = _launch_agent_in_pane_sync("$1", "opencode", None, None)

        assert result == {"status": "success"}
        mock_pane.send_keys.assert_called_once_with("opencode", enter=True)

    @patch("waggle.tmux.libtmux.Server")
    def test_appends_settings_to_command(self, mock_server_cls):
        """Verify extra settings flags are appended to the agent command."""
        mock_server = MagicMock()
        mock_session = MagicMock()
        mock_pane = MagicMock()
        mock_session.active_window.active_pane = mock_pane
        mock_server.sessions.get.return_value = mock_session
        mock_server_cls.return_value = mock_server

        result = _launch_agent_in_pane_sync("$1", "claude", None, "--dangerously-skip-permissions")

        assert result == {"status": "success"}
        mock_pane.send_keys.assert_called_once_with(
            "claude --dangerously-skip-permissions", enter=True
        )

    @patch("waggle.tmux.libtmux.Server")
    def test_model_and_settings_combined(self, mock_server_cls):
        """Verify both model and settings are included in the command."""
        mock_server = MagicMock()
        mock_session = MagicMock()
        mock_pane = MagicMock()
        mock_session.active_window.active_pane = mock_pane
        mock_server.sessions.get.return_value = mock_session
        mock_server_cls.return_value = mock_server

        result = _launch_agent_in_pane_sync("$1", "claude", "haiku", "--no-interactive")

        assert result == {"status": "success"}
        call_args = mock_pane.send_keys.call_args[0][0]
        assert "claude" in call_args
        assert "--model haiku" in call_args
        assert "--no-interactive" in call_args

    @patch("waggle.tmux.libtmux.Server")
    def test_libtmux_exception_caught(self, mock_server_cls):
        """Verify LibTmuxException is caught and returned as error dict."""
        mock_server = MagicMock()
        mock_server.sessions.get.side_effect = LibTmuxException("no session")
        mock_server_cls.return_value = mock_server

        result = _launch_agent_in_pane_sync("$1", "claude", None, None)

        assert result["status"] == "error"
        assert result["message"]


class TestLaunchAgentInPaneAsync:
    """Tests for launch_agent_in_pane() — async wrapper."""

    @pytest.mark.asyncio
    @patch("waggle.tmux._launch_agent_in_pane_sync")
    async def test_delegates_to_sync(self, mock_sync):
        """Verify launch_agent_in_pane delegates to _launch_agent_in_pane_sync."""
        mock_sync.return_value = {"status": "success"}

        result = await launch_agent_in_pane("$1", "claude", "sonnet", "--no-interactive")

        mock_sync.assert_called_once_with("$1", "claude", "sonnet", "--no-interactive")
        assert result == {"status": "success"}


class TestResolveSessionSync:
    """Tests for _resolve_session_sync() — 4-case session resolution logic (SR-6.2)."""

    @patch("waggle.tmux.libtmux.Server")
    def test_session_not_found_returns_create(self, mock_server_cls):
        """Case 1: Session doesn't exist → action='create'."""
        mock_server = MagicMock()
        mock_server.sessions.get.side_effect = Exception("session not found")
        mock_server_cls.return_value = mock_server

        result = _resolve_session_sync("new-session", "/repo")

        assert result == {"action": "create"}

    @patch("waggle.tmux.libtmux.Server")
    def test_llm_running_returns_error(self, mock_server_cls):
        """Case 2: Session exists + LLM running → error 'LLM already running'."""
        mock_server = MagicMock()
        mock_session = MagicMock()
        mock_pane = MagicMock()
        mock_pane.pane_current_command = "claude"
        mock_session.active_window.active_pane = mock_pane
        mock_server.sessions.get.return_value = mock_session
        mock_server_cls.return_value = mock_server

        result = _resolve_session_sync("existing-session", "/repo")

        assert result["action"] == "error"
        assert "LLM already running" in result["message"]

    @patch("waggle.tmux.libtmux.Server")
    def test_no_llm_same_repo_returns_reuse(self, mock_server_cls, tmp_path):
        """Case 3: Session exists + no LLM + same repo → action='reuse'."""
        mock_server = MagicMock()
        mock_session = MagicMock()
        mock_pane = MagicMock()
        mock_pane.pane_current_command = "zsh"
        mock_session.active_window.active_pane = mock_pane
        mock_session.session_path = str(tmp_path)
        mock_session.session_id = "$3"
        mock_session.session_name = "existing-session"
        mock_session.session_created = "1700000001"
        mock_server.sessions.get.return_value = mock_session
        mock_server_cls.return_value = mock_server

        result = _resolve_session_sync("existing-session", str(tmp_path))

        assert result["action"] == "reuse"
        assert result["session_id"] == "$3"
        assert result["session_name"] == "existing-session"

    @patch("waggle.tmux.libtmux.Server")
    def test_no_llm_different_repo_returns_error(self, mock_server_cls):
        """Case 4: Session exists + no LLM + different repo → error 'wrong repo'."""
        mock_server = MagicMock()
        mock_session = MagicMock()
        mock_pane = MagicMock()
        mock_pane.pane_current_command = "bash"
        mock_session.active_window.active_pane = mock_pane
        mock_session.session_path = "/some/other/path"
        mock_server.sessions.get.return_value = mock_session
        mock_server_cls.return_value = mock_server

        result = _resolve_session_sync("existing-session", "/my/repo")

        assert result["action"] == "error"
        assert "wrong repo" in result["message"]

    @patch("waggle.tmux.libtmux.Server")
    def test_libtmux_exception_returns_error(self, mock_server_cls):
        """Verify LibTmuxException from server init is caught as error."""
        mock_server_cls.side_effect = LibTmuxException("tmux unavailable")

        result = _resolve_session_sync("session", "/repo")

        assert result["action"] == "error"
        assert result["message"]


class TestResolveSessionAsync:
    """Tests for resolve_session() — async wrapper."""

    @pytest.mark.asyncio
    @patch("waggle.tmux._resolve_session_sync")
    async def test_delegates_to_sync(self, mock_sync):
        """Verify resolve_session delegates to _resolve_session_sync."""
        mock_sync.return_value = {"action": "create"}

        result = await resolve_session("session", "/repo")

        mock_sync.assert_called_once_with("session", "/repo")
        assert result == {"action": "create"}
