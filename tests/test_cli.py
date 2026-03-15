"""Unit tests for the CLI dispatcher."""

import sys
import json

import pytest
from unittest.mock import patch, AsyncMock

from waggle.cli import main


class TestCLIHelp:
    def test_help_exits_0(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["waggle", "--help"])
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0

    def test_serve_help_exits_0(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["waggle", "serve", "--help"])
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0

    def test_no_subcommand_exits_0(self, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv", ["waggle"])
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "usage:" in captured.out.lower()


class TestServeSubcommand:
    def test_serve_calls_server_run(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["waggle", "serve"])
        with patch("waggle.server.run") as mock_run:
            main()
            mock_run.assert_called_once_with()


class TestUsageErrors:
    def test_usage_error_writes_json_to_stdout_exits_2(self, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv", ["waggle", "--bogus-flag"])
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 2
        captured = capsys.readouterr()
        assert '{"status": "error"' in captured.out

    def test_usage_error_does_not_write_to_stderr(self, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv", ["waggle", "--bogus-flag"])
        with pytest.raises(SystemExit):
            main()
        captured = capsys.readouterr()
        assert captured.err == ""


class TestListAgents:
    def test_list_agents_defaults(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["waggle", "list-agents"])
        with patch("waggle.server.list_agents", new_callable=AsyncMock) as mock_fn:
            mock_fn.return_value = {"status": "success", "agents": []}
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 0
            mock_fn.assert_called_once_with(name=None, repo=None, ctx=None)

    def test_list_agents_filters(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["waggle", "list-agents", "--name", "foo", "--repo", "/bar"])
        with patch("waggle.server.list_agents", new_callable=AsyncMock) as mock_fn:
            mock_fn.return_value = {"status": "success", "agents": []}
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 0
            mock_fn.assert_called_once_with(name="foo", repo="/bar", ctx=None)

    def test_list_agents_passes_args(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["waggle", "list-agents", "--name", "foo"])
        with patch("waggle.server.list_agents", new_callable=AsyncMock) as mock_fn:
            mock_fn.return_value = {"status": "success", "agents": []}
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 0
            mock_fn.assert_called_once_with(name="foo", repo=None, ctx=None)


class TestSpawnAgent:
    def test_spawn_agent_calls_function(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", [
            "waggle", "spawn-agent", "--repo", "/r", "--session-name", "s", "--agent", "claude"
        ])
        with patch("waggle.server.spawn_agent", new_callable=AsyncMock) as mock_fn:
            mock_fn.return_value = {"status": "success"}
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 0
            mock_fn.assert_called_once_with(
                "/r", "s", "claude",
                model=None, command=None, settings=None, ctx=None
            )


class TestDeleteRepoAgents:
    def test_delete_repo_agents_default_cwd(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["waggle", "delete-repo-agents"])
        with patch("waggle.server.delete_repo_agents", new_callable=AsyncMock) as mock_fn:
            mock_fn.return_value = {"status": "success"}
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 0
            mock_fn.assert_called_once()

    def test_delete_repo_agents_explicit_root(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["waggle", "delete-repo-agents", "--repo-root", "/some/path"])
        with patch("waggle.server.delete_repo_agents", new_callable=AsyncMock) as mock_fn:
            mock_fn.return_value = {"status": "success"}
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 0
            mock_fn.assert_called_once_with(repo_root="/some/path", ctx=None)


class TestCloseSession:
    def test_close_session_force_flag(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["waggle", "close-session", "--session-id", "$1", "--force"])
        with patch("waggle.server.close_session", new_callable=AsyncMock) as mock_fn:
            mock_fn.return_value = {"status": "success"}
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 0
            mock_fn.assert_called_once_with("$1", session_name=None, force=True)


class TestLifecycleExitCodes:
    def test_lifecycle_exits_0_on_success(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["waggle", "list-agents"])
        with patch("waggle.server.list_agents", new_callable=AsyncMock) as mock_fn:
            mock_fn.return_value = {"status": "success", "agents": []}
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 0

    def test_lifecycle_exits_1_on_error(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["waggle", "list-agents"])
        with patch("waggle.server.list_agents", new_callable=AsyncMock) as mock_fn:
            mock_fn.return_value = {"status": "error", "message": "db down"}
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 1
