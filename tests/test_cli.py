"""Unit tests for the CLI dispatcher."""

import sys

import pytest
from unittest.mock import patch

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
    def test_serve_calls_daemon_run(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["waggle", "serve"])
        with patch("waggle.daemon.run") as mock_run:
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


class TestSetStateSubcommand:
    def test_set_state_help_exits_0(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["waggle", "set-state", "--help"])
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0

    def test_set_state_calls_handler(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["waggle", "set-state"])
        with patch("waggle.cli._handle_set_state") as mock_handler:
            main()
            mock_handler.assert_called_once()
            args = mock_handler.call_args[0][0]
            assert args.delete is False

    def test_set_state_delete_flag(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["waggle", "set-state", "--delete"])
        with patch("waggle.cli._handle_set_state") as mock_handler:
            main()
            mock_handler.assert_called_once()
            args = mock_handler.call_args[0][0]
            assert args.delete is True


class TestStingSubcommand:
    def test_sting_calls_handle_sting(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["waggle", "sting"])
        with patch("waggle.sting.handle_sting") as mock_handler:
            main()
            mock_handler.assert_called_once()
