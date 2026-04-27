"""Unit tests for waggle.sting module."""
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from waggle.sting import (
    _CLI_REFERENCE,
    _WAGGLE_PATTERN,
    _detect_mcp,
    _has_waggle_in_mcp_servers,
    _key_matches_waggle,
    handle_sting,
)


class TestWagglePattern:
    def test_pattern_matches_exact(self):
        assert _WAGGLE_PATTERN.search("waggle")

    def test_pattern_matches_with_suffix(self):
        assert _WAGGLE_PATTERN.search("waggle-mcp")
        assert _WAGGLE_PATTERN.search("waggle_server")

    def test_pattern_matches_with_prefix(self):
        assert _WAGGLE_PATTERN.search("my-waggle")
        assert _WAGGLE_PATTERN.search("my_waggle")

    def test_pattern_no_match_embedded(self):
        assert not _WAGGLE_PATTERN.search("wagglefish")
        assert not _WAGGLE_PATTERN.search("mywaggle")

    def test_pattern_case_insensitive(self):
        assert _WAGGLE_PATTERN.search("WAGGLE")
        assert _WAGGLE_PATTERN.search("Waggle-Mcp")


class TestDetectMcp:
    def test_detect_from_claude_json(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        claude_json = tmp_path / ".claude.json"
        claude_json.write_text(json.dumps({"mcpServers": {"waggle": {}}}))
        assert _detect_mcp() is True

    def test_detect_from_settings_json(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        settings = tmp_path / ".claude" / "settings.json"
        settings.parent.mkdir(parents=True)
        settings.write_text(json.dumps({"mcpServers": {"waggle-server": {}}}))
        assert _detect_mcp() is True

    def test_not_found_when_no_config(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        assert _detect_mcp() is False

    def test_malformed_json_returns_false(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        (tmp_path / ".claude.json").write_text("{not valid json")
        assert _detect_mcp() is False

    def test_no_waggle_key_returns_false(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        (tmp_path / ".claude.json").write_text(json.dumps({"mcpServers": {"other-tool": {}}}))
        assert _detect_mcp() is False


class TestHandleSting:
    def test_silent_when_detected(self, monkeypatch, capsys):
        monkeypatch.setattr("waggle.sting._detect_mcp", lambda: True)
        monkeypatch.setattr(sys, "argv", ["waggle", "sting"])
        with pytest.raises(SystemExit) as exc:
            handle_sting(None)
        assert exc.value.code == 0
        assert capsys.readouterr().out == ""

    def test_prints_reference_when_not_detected(self, monkeypatch, capsys):
        monkeypatch.setattr("waggle.sting._detect_mcp", lambda: False)
        monkeypatch.setattr(sys, "argv", ["waggle", "sting"])
        with pytest.raises(SystemExit) as exc:
            handle_sting(None)
        assert exc.value.code == 0
        assert "serve" in capsys.readouterr().out


class TestCliReference:
    def test_contains_all_subcommands(self):
        for cmd in ["serve", "set-state", "sting"]:
            assert cmd in _CLI_REFERENCE, f"_CLI_REFERENCE missing: {cmd}"
