"""Unit tests for the CLI dispatcher."""

import sys
import json

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
