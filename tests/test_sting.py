"""Unit tests for claude_spawn.sting module."""
import json
from unittest.mock import patch

import pytest

from claude_spawn.sting import check_claude_status_health, handle_sting
from tests.helpers import fake_claude_status
from tests.sample_payloads import (
    CAPABILITIES_V1,
    CAPABILITIES_V2,
    STDERR_ERR_STORE_UNAVAILABLE,
)


class TestCheckClaudeStatusHealth:
    """Tests for the new check_claude_status_health() function."""

    def test_green_when_capabilities_v1(self):
        payload = json.dumps(CAPABILITIES_V1)
        with fake_claude_status([(payload, "", 0)]):
            healthy, msg = check_claude_status_health()
        assert healthy is True
        assert "OK" in msg

    def test_green_message_includes_version(self):
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
        payload = json.dumps(CAPABILITIES_V2)
        with fake_claude_status([(payload, "", 0)]):
            with pytest.raises(SystemExit) as exc:
                handle_sting(None)
        assert exc.value.code == 1
