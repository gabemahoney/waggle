"""Unit tests for claude_spawn.spawn.spawn_worker_impl (SR-3.2, SR-1.1).

All tmux invocations are patched via claude_spawn.spawn._tmux.
No real tmux process is forked.  No conftest.py.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

import claude_spawn.spawn as sp
from tests.helpers import (
    fake_claude_status,
    fake_templates_dir,
    fake_worker_record,
    fake_workers_response,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_OK_TRIPLE = ("", "", 0)   # tmux exits 0 with no output

# Fixed instance_id used in happy-path tests that need a known ID.
_TEST_IID = "10000000-0000-4000-8000-000000000001"


def _patch_tmux(triples):
    """Context manager: patch claude_spawn.spawn._tmux to return canned triples."""
    queue = list(triples)
    calls = []

    def side_effect(argv):
        calls.append(list(argv))
        if not queue:
            raise AssertionError(f"_tmux called more times than expected; argv={argv!r}")
        return queue.pop(0)

    patcher = patch("claude_spawn.spawn._tmux", side_effect=side_effect)
    patcher.start()
    return calls, patcher


def _empty_workers_triple() -> tuple[str, str, int]:
    """Success triple: empty workers list (no collision, not yet registered)."""
    return (json.dumps({"workers": [], "skipped": []}), "", 0)


def _readiness_triple(iid: str) -> tuple[str, str, int]:
    """Success triple: workers list containing *iid* (readiness matched)."""
    rec = fake_worker_record(instance_id=iid, status="working", cwd="/tmp")
    return (json.dumps(fake_workers_response([rec])), "", 0)


def _cs_happy_triples(iid: str) -> list[tuple[str, str, int]]:
    """Two-triple list for happy-path tests that supply an explicit instance_id.

    Triple 0: precheck — empty workers (no ErrInstanceIdCollision).
    Triple 1: readiness poll — worker registered on the first poll.
    """
    return [_empty_workers_triple(), _readiness_triple(iid)]


# ---------------------------------------------------------------------------
# Return shape
# ---------------------------------------------------------------------------


class TestSpawnWorkerShape:
    def test_returns_instance_id_and_tmux_session_name(self):
        calls, patcher = _patch_tmux([_OK_TRIPLE, _OK_TRIPLE])
        try:
            with fake_claude_status(_cs_happy_triples(_TEST_IID)):
                result = sp.spawn_worker_impl(cwd="/tmp", instance_id=_TEST_IID)
        finally:
            patcher.stop()
        assert "instance_id" in result
        assert "tmux_session_name" in result
        assert "session_name" not in result, "old 'session_name' key must be absent"

    def test_instance_id_is_uuid_format(self):
        import uuid
        calls, patcher = _patch_tmux([_OK_TRIPLE, _OK_TRIPLE])
        try:
            with fake_claude_status(_cs_happy_triples(_TEST_IID)):
                result = sp.spawn_worker_impl(cwd="/tmp", instance_id=_TEST_IID)
        finally:
            patcher.stop()
        # Must parse without raising
        uuid.UUID(result["instance_id"])

    def test_default_session_name_format(self):
        """Default tmux_session_name is <sanitize(cwd)>-<instance_id[:8]>."""
        calls, patcher = _patch_tmux([_OK_TRIPLE, _OK_TRIPLE])
        try:
            with fake_claude_status(_cs_happy_triples(_TEST_IID)):
                result = sp.spawn_worker_impl(cwd="/tmp", instance_id=_TEST_IID)
        finally:
            patcher.stop()
        # With cwd="/tmp", sanitize → "tmp"
        assert result["tmux_session_name"].startswith("tmp-")

    def test_default_session_name_uses_first_8_chars_of_instance_id(self):
        """tmux_session_name suffix is exactly instance_id[:8] (raw slice)."""
        calls, patcher = _patch_tmux([_OK_TRIPLE, _OK_TRIPLE])
        try:
            with fake_claude_status(_cs_happy_triples(_TEST_IID)):
                result = sp.spawn_worker_impl(cwd="/tmp", instance_id=_TEST_IID)
        finally:
            patcher.stop()
        iid = result["instance_id"]
        expected = f"{sp._sanitize_folder_name('/tmp')}-{iid[:8]}"
        assert result["tmux_session_name"] == expected

    def test_explicit_tmux_session_name_is_used(self):
        calls, patcher = _patch_tmux([_OK_TRIPLE, _OK_TRIPLE])
        try:
            with fake_claude_status(_cs_happy_triples(_TEST_IID)):
                result = sp.spawn_worker_impl(
                    cwd="/tmp", tmux_session_name="my-session", instance_id=_TEST_IID
                )
        finally:
            patcher.stop()
        assert result["tmux_session_name"] == "my-session"


# ---------------------------------------------------------------------------
# Required env vars in tmux new-session call
# ---------------------------------------------------------------------------


class TestSpawnWorkerEnvVars:
    def _run_and_get_new_session_argv(self, model=None, repo="/tmp", sn=None):
        calls, patcher = _patch_tmux([_OK_TRIPLE, _OK_TRIPLE])
        try:
            with fake_claude_status(_cs_happy_triples(_TEST_IID)):
                sp.spawn_worker_impl(
                    cwd=repo, model=model, tmux_session_name=sn,
                    instance_id=_TEST_IID,
                )
        finally:
            patcher.stop()
        # First call is new-session
        return calls[0]

    def _env_pairs(self, argv):
        """Extract {KEY: VALUE} from -e KEY=VALUE pairs in argv."""
        pairs = {}
        i = 0
        while i < len(argv):
            if argv[i] == "-e" and i + 1 < len(argv):
                key, _, val = argv[i + 1].partition("=")
                pairs[key] = val
                i += 2
            else:
                i += 1
        return pairs

    def test_new_session_is_first_call(self):
        argv = self._run_and_get_new_session_argv()
        assert argv[0] == "new-session"

    def test_detached_flag_present(self):
        argv = self._run_and_get_new_session_argv()
        assert "-d" in argv

    def test_session_name_flag_present(self):
        argv = self._run_and_get_new_session_argv(sn="test-sess")
        assert "-s" in argv
        idx = argv.index("-s")
        assert argv[idx + 1] == "test-sess"

    def test_claude_status_instance_id_present(self):
        argv = self._run_and_get_new_session_argv()
        pairs = self._env_pairs(argv)
        assert "CLAUDE_STATUS_INSTANCE_ID" in pairs
        assert pairs["CLAUDE_STATUS_INSTANCE_ID"]  # non-empty

    def test_relay_mode_on(self):
        argv = self._run_and_get_new_session_argv()
        pairs = self._env_pairs(argv)
        assert pairs.get("CLAUDE_STATUS_RELAY_MODE") == "on"

    def test_auq_mode_record(self):
        argv = self._run_and_get_new_session_argv()
        pairs = self._env_pairs(argv)
        assert pairs.get("CLAUDE_STATUS_AUQ_MODE") == "record"

    def test_claude_spawn_owned_label_1(self):
        argv = self._run_and_get_new_session_argv()
        pairs = self._env_pairs(argv)
        assert pairs.get("CLAUDE_STATUS_LABEL_CLAUDE_SPAWN_OWNED") == "1"

    def test_claude_spawn_session_name_label(self):
        argv = self._run_and_get_new_session_argv(sn="test-sess")
        pairs = self._env_pairs(argv)
        assert pairs.get("CLAUDE_STATUS_LABEL_CLAUDE_SPAWN_SESSION_NAME") == "test-sess"

    def test_claude_spawn_model_label_lowercased_when_model_supplied(self):
        """Model label is present and lowercased when model is supplied."""
        argv = self._run_and_get_new_session_argv(model="Claude-Sonnet-4-5")
        pairs = self._env_pairs(argv)
        assert pairs.get("CLAUDE_STATUS_LABEL_CLAUDE_SPAWN_MODEL") == "claude-sonnet-4-5"

    def test_claude_spawn_model_label_absent_when_model_omitted(self):
        """Model label is NOT emitted when model is omitted (conditional label)."""
        argv = self._run_and_get_new_session_argv(model=None)
        pairs = self._env_pairs(argv)
        assert "CLAUDE_STATUS_LABEL_CLAUDE_SPAWN_MODEL" not in pairs

    def test_claude_spawn_cwd_label(self):
        argv = self._run_and_get_new_session_argv(repo="/tmp")
        pairs = self._env_pairs(argv)
        assert pairs.get("CLAUDE_STATUS_LABEL_CLAUDE_SPAWN_CWD") == "/tmp"

    def test_all_required_env_vars_present(self):
        """All unconditional SR-4.2 env vars are in the new-session argv."""
        argv = self._run_and_get_new_session_argv()
        pairs = self._env_pairs(argv)
        for key in sp._REQUIRED_ENV_VARS:
            assert key in pairs, f"missing required env var {key!r}"

    def test_required_env_vars_excludes_model_label(self):
        """_REQUIRED_ENV_VARS must NOT contain the conditional MODEL label."""
        assert "CLAUDE_STATUS_LABEL_CLAUDE_SPAWN_MODEL" not in sp._REQUIRED_ENV_VARS


# ---------------------------------------------------------------------------
# Claude launch command — window 0, pane 0
# ---------------------------------------------------------------------------


class TestSpawnWorkerLaunch:
    def test_send_keys_is_second_call(self):
        calls, patcher = _patch_tmux([_OK_TRIPLE, _OK_TRIPLE])
        try:
            with fake_claude_status(_cs_happy_triples(_TEST_IID)):
                sp.spawn_worker_impl(cwd="/tmp", tmux_session_name="s1", instance_id=_TEST_IID)
        finally:
            patcher.stop()
        assert calls[1][0] == "send-keys"

    def test_send_keys_targets_window_0_pane_0(self):
        calls, patcher = _patch_tmux([_OK_TRIPLE, _OK_TRIPLE])
        try:
            with fake_claude_status(_cs_happy_triples(_TEST_IID)):
                sp.spawn_worker_impl(cwd="/tmp", tmux_session_name="s1", instance_id=_TEST_IID)
        finally:
            patcher.stop()
        argv = calls[1]
        assert "-t" in argv
        idx = argv.index("-t")
        target = argv[idx + 1]
        assert target == "s1:0.0"

    def test_send_keys_sends_claude_model_command_when_model_supplied(self):
        """--model flag appears in send-keys when model is supplied."""
        calls, patcher = _patch_tmux([_OK_TRIPLE, _OK_TRIPLE])
        try:
            with fake_claude_status(_cs_happy_triples(_TEST_IID)):
                sp.spawn_worker_impl(
                    cwd="/tmp", model="opus", tmux_session_name="s1",
                    instance_id=_TEST_IID,
                )
        finally:
            patcher.stop()
        argv = calls[1]
        cmd_parts = " ".join(argv)
        assert "claude" in cmd_parts
        assert "--model opus" in cmd_parts

    def test_send_keys_no_model_flag_when_model_omitted(self):
        """--model flag absent from send-keys when model is not supplied."""
        calls, patcher = _patch_tmux([_OK_TRIPLE, _OK_TRIPLE])
        try:
            with fake_claude_status(_cs_happy_triples(_TEST_IID)):
                sp.spawn_worker_impl(cwd="/tmp", tmux_session_name="s1", instance_id=_TEST_IID)
        finally:
            patcher.stop()
        cmd_parts = " ".join(calls[1])
        assert "--model" not in cmd_parts

    def test_send_keys_includes_enter(self):
        calls, patcher = _patch_tmux([_OK_TRIPLE, _OK_TRIPLE])
        try:
            with fake_claude_status(_cs_happy_triples(_TEST_IID)):
                sp.spawn_worker_impl(cwd="/tmp", tmux_session_name="s1", instance_id=_TEST_IID)
        finally:
            patcher.stop()
        assert "Enter" in calls[1]


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


class TestSpawnWorkerErrors:
    def test_new_session_failure_returns_operation_failed(self):
        calls, patcher = _patch_tmux([("", "session already exists", 1)])
        try:
            result = sp.spawn_worker_impl(cwd="/tmp")
        finally:
            patcher.stop()
        assert result.get("ok") is False
        assert result.get("err_name") == "ErrTmuxSessionCreate"

    def test_send_keys_failure_returns_operation_failed(self):
        calls, patcher = _patch_tmux([_OK_TRIPLE, ("", "no such session", 1)])
        try:
            result = sp.spawn_worker_impl(cwd="/tmp")
        finally:
            patcher.stop()
        assert result.get("ok") is False
        assert result.get("err_name") == "ErrTmuxSendKeys"

    def test_exactly_two_tmux_calls_on_success(self):
        """Worker found on first readiness poll → exactly 2 _tmux calls (new-session + send-keys)."""
        calls, patcher = _patch_tmux([_OK_TRIPLE, _OK_TRIPLE])
        try:
            with fake_claude_status(_cs_happy_triples(_TEST_IID)):
                sp.spawn_worker_impl(cwd="/tmp", instance_id=_TEST_IID)
        finally:
            patcher.stop()
        assert len(calls) == 2

    def test_one_tmux_call_on_new_session_failure(self):
        calls, patcher = _patch_tmux([("", "err", 1)])
        try:
            sp.spawn_worker_impl(cwd="/tmp")
        finally:
            patcher.stop()
        assert len(calls) == 1


# ---------------------------------------------------------------------------
# Old-signature rejection (Epic 1 AC1)
# ---------------------------------------------------------------------------


class TestOldSignatureRejection:
    def test_impl_rejects_old_positional_shape(self):
        """spawn_worker_impl("opus", "/tmp", "name") must NOT produce a success.

        With the new 12-option signature the positional slots are
        (cwd, template, model, ...), so passing the legacy (model, repo,
        session_name) shape as positionals maps "opus" to cwd, "/tmp" to
        template, "name" to model.

        Wrapping in fake_templates_dir({}) ensures the template loader fires
        first and returns ErrTemplateNotFound for the "/tmp" template name —
        regardless of whether ~/.claude-spawn/templates/ exists on the host.
        """
        with fake_templates_dir({}):
            result = sp.spawn_worker_impl("opus", "/tmp", "name")
        # The old positional shape must not succeed (no instance_id key).
        assert "instance_id" not in result, (
            "old positional shape must not produce a successful result"
        )
        assert result.get("ok") is False
        assert result.get("err_name") == "ErrTemplateNotFound", (
            f"unexpected err_name: {result.get('err_name')!r}"
        )
