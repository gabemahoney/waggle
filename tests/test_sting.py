"""Unit tests for waggle.sting module."""
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from claude_spawn.sting import (
    _CLAUDE_SPAWN_PATTERN,
    _detect_mcp,
    _has_claude_spawn_in_mcp_servers,
    _key_matches_claude_spawn,
    check_claude_status_health,
    handle_sting,
)
from tests.helpers import fake_claude_status
from tests.sample_payloads import (
    CAPABILITIES_V1,
    CAPABILITIES_V2,
    STDERR_ERR_STORE_UNAVAILABLE,
)


class TestClaudeSpawnPattern:
    def test_pattern_matches_exact(self):
        assert _CLAUDE_SPAWN_PATTERN.search("claude-spawn")
        assert _CLAUDE_SPAWN_PATTERN.search("claude_spawn")

    def test_pattern_matches_with_suffix(self):
        assert _CLAUDE_SPAWN_PATTERN.search("claude_spawn_server")

    def test_pattern_matches_with_prefix(self):
        assert _CLAUDE_SPAWN_PATTERN.search("my-claude-spawn")

    def test_pattern_no_match_embedded(self):
        assert not _CLAUDE_SPAWN_PATTERN.search("claudespawn")
        assert not _CLAUDE_SPAWN_PATTERN.search("myclaudespawn")
        assert not _CLAUDE_SPAWN_PATTERN.search("claude-spawnfish")
        assert not _CLAUDE_SPAWN_PATTERN.search("claude-spawned")

    def test_pattern_case_insensitive(self):
        assert _CLAUDE_SPAWN_PATTERN.search("CLAUDE-SPAWN")
        assert _CLAUDE_SPAWN_PATTERN.search("Claude-Spawn")


class TestDetectMcp:
    def test_detect_from_claude_json(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        claude_json = tmp_path / ".claude.json"
        claude_json.write_text(json.dumps({"mcpServers": {"claude-spawn": {}}}))
        assert _detect_mcp() is True

    def test_detect_from_settings_json(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        settings = tmp_path / ".claude" / "settings.json"
        settings.parent.mkdir(parents=True)
        settings.write_text(json.dumps({"mcpServers": {"claude-spawn-server": {}}}))
        assert _detect_mcp() is True

    def test_not_found_when_no_config(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        assert _detect_mcp() is False

    def test_malformed_json_returns_false(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        (tmp_path / ".claude.json").write_text("{not valid json")
        assert _detect_mcp() is False

    def test_no_claude_spawn_key_returns_false(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        (tmp_path / ".claude.json").write_text(json.dumps({"mcpServers": {"other-tool": {}}}))
        assert _detect_mcp() is False


class TestCheckClaudeStatusHealth:
    """Tests for the new check_claude_status_health() function."""

    def test_green_when_capabilities_v1(self):
        import json
        payload = json.dumps(CAPABILITIES_V1)
        with fake_claude_status([(payload, "", 0)]):
            healthy, msg = check_claude_status_health()
        assert healthy is True
        assert "OK" in msg

    def test_green_message_includes_version(self):
        import json
        payload = json.dumps(CAPABILITIES_V1)
        with fake_claude_status([(payload, "", 0)]):
            healthy, msg = check_claude_status_health()
        assert "1.0.0" in msg

    def test_red_when_binary_missing(self):
        with patch("claude_spawn.claude_status._run", side_effect=FileNotFoundError):
            healthy, msg = check_claude_status_health()
        assert healthy is False
        assert "PATH" in msg or "install" in msg.lower()

    def test_red_when_contract_version_mismatch(self):
        import json
        payload = json.dumps(CAPABILITIES_V2)
        with fake_claude_status([(payload, "", 0)]):
            healthy, msg = check_claude_status_health()
        assert healthy is False
        assert "mismatch" in msg.lower() or "ErrContractVersionMismatch" in msg

    def test_red_when_store_unavailable(self):
        with fake_claude_status([("", STDERR_ERR_STORE_UNAVAILABLE, 1)]):
            healthy, msg = check_claude_status_health()
        assert healthy is False
        assert "ErrStoreUnavailable" in msg or "unavailable" in msg.lower()


class TestHandleSting:
    def test_exits_0_when_healthy(self, capsys):
        import json
        payload = json.dumps(CAPABILITIES_V1)
        with fake_claude_status([(payload, "", 0)]):
            with pytest.raises(SystemExit) as exc:
                handle_sting(None)
        assert exc.value.code == 0
        assert capsys.readouterr().out.strip()  # some status output

    def test_exits_1_when_binary_missing(self, capsys):
        with patch("claude_spawn.claude_status._run", side_effect=FileNotFoundError):
            with pytest.raises(SystemExit) as exc:
                handle_sting(None)
        assert exc.value.code == 1

    def test_exits_1_when_contract_mismatch(self, capsys):
        import json
        payload = json.dumps(CAPABILITIES_V2)
        with fake_claude_status([(payload, "", 0)]):
            with pytest.raises(SystemExit) as exc:
                handle_sting(None)
        assert exc.value.code == 1

