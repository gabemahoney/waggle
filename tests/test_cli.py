"""Unit tests for the CLI dispatcher (surviving subcommands only)."""

import sys

import pytest
from unittest.mock import patch

from claude_spawn.cli import main


class TestCLIHelp:
    def test_help_exits_0(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["claude-spawn", "--help"])
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


class TestUsageErrors:
    def test_usage_error_writes_json_to_stdout_exits_2(self, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv", ["claude-spawn", "--bogus-flag"])
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 2
        captured = capsys.readouterr()
        assert '{"status": "error"' in captured.out

    def test_usage_error_does_not_write_to_stderr(self, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv", ["claude-spawn", "--bogus-flag"])
        with pytest.raises(SystemExit):
            main()
        captured = capsys.readouterr()
        assert captured.err == ""


class TestRemovedSubcommands:
    """Verify daemon-era subcommands are gone."""

    @pytest.mark.parametrize("sub", ["serve", "set-state", "permission-request", "ask-relay"])
    def test_removed_subcommand_exits_nonzero(self, sub, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["claude-spawn", sub])
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code != 0


class TestStingSubcommand:
    def test_sting_calls_handle_sting(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["claude-spawn", "sting"])
        with patch("claude_spawn.sting.handle_sting") as mock_handler:
            main()
            mock_handler.assert_called_once()


class TestMcpSubcommand:
    def test_mcp_calls_run(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["claude-spawn", "mcp"])
        with patch("claude_spawn.mcp_stdio.run") as mock_run:
            main()
            mock_run.assert_called_once_with()

    def test_mcp_help_exits_0(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["claude-spawn", "mcp", "--help"])
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0


class TestInstallSubcommand:
    def test_install_calls_handle_install(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["claude-spawn", "install"])
        with patch("claude_spawn.installer.handle_install") as mock_handler:
            main()
            mock_handler.assert_called_once()

    def test_install_auq_order_forwarded(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["claude-spawn", "install", "--auq-order", "last"])
        with patch("claude_spawn.installer.handle_install") as mock_handler:
            main()
            args = mock_handler.call_args[0][0]
            assert args.auq_order == "last"

    def test_install_help_exits_0(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["claude-spawn", "install", "--help"])
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0
