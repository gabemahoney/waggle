"""Unit tests for waggle.spawn.spawn_worker_impl (SR-3.2).

All tmux invocations are patched via waggle.spawn._tmux.
No real tmux process is forked.  No conftest.py.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

import claude_spawn.spawn as sp


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_OK_TRIPLE = ("", "", 0)   # tmux exits 0 with no output


def _patch_tmux(triples):
    """Context manager: patch waggle.spawn._tmux to return canned triples."""
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


# ---------------------------------------------------------------------------
# Return shape
# ---------------------------------------------------------------------------


class TestSpawnWorkerShape:
    def test_returns_instance_id_and_session_name(self):
        calls, patcher = _patch_tmux([_OK_TRIPLE, _OK_TRIPLE])
        try:
            result = sp.spawn_worker_impl("claude-sonnet-4-5", "/tmp/repo")
        finally:
            patcher.stop()
        assert "instance_id" in result
        assert "session_name" in result

    def test_instance_id_is_uuid_format(self):
        import uuid
        calls, patcher = _patch_tmux([_OK_TRIPLE, _OK_TRIPLE])
        try:
            result = sp.spawn_worker_impl("claude-sonnet-4-5", "/tmp/repo")
        finally:
            patcher.stop()
        # Must parse without raising
        uuid.UUID(result["instance_id"])

    def test_default_session_name_starts_with_waggle(self):
        calls, patcher = _patch_tmux([_OK_TRIPLE, _OK_TRIPLE])
        try:
            result = sp.spawn_worker_impl("claude-sonnet-4-5", "/tmp/repo")
        finally:
            patcher.stop()
        assert result["session_name"].startswith("waggle-")

    def test_default_session_name_uses_first_8_chars_of_instance_id(self):
        calls, patcher = _patch_tmux([_OK_TRIPLE, _OK_TRIPLE])
        try:
            result = sp.spawn_worker_impl("claude-sonnet-4-5", "/tmp/repo")
        finally:
            patcher.stop()
        # waggle-<first 8 chars of uuid (without dashes)>
        iid_nodashes = result["instance_id"].replace("-", "")
        expected_suffix = iid_nodashes[:8]
        assert result["session_name"] == f"waggle-{expected_suffix}" or \
               result["session_name"] == f"waggle-{result['instance_id'][:8]}"

    def test_explicit_session_name_is_used(self):
        calls, patcher = _patch_tmux([_OK_TRIPLE, _OK_TRIPLE])
        try:
            result = sp.spawn_worker_impl("claude-sonnet-4-5", "/tmp/repo", session_name="my-session")
        finally:
            patcher.stop()
        assert result["session_name"] == "my-session"


# ---------------------------------------------------------------------------
# Required env vars in tmux new-session call
# ---------------------------------------------------------------------------


class TestSpawnWorkerEnvVars:
    def _run_and_get_new_session_argv(self, model="claude-sonnet-4-5", repo="/tmp/repo", sn=None):
        calls, patcher = _patch_tmux([_OK_TRIPLE, _OK_TRIPLE])
        try:
            sp.spawn_worker_impl(model, repo, sn)
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
        assert pairs["CLAUDE_STATUS_INSTANCE_ID"]  # non-empty UUID

    def test_relay_mode_on(self):
        argv = self._run_and_get_new_session_argv()
        pairs = self._env_pairs(argv)
        assert pairs.get("CLAUDE_STATUS_RELAY_MODE") == "on"

    def test_auq_mode_record(self):
        argv = self._run_and_get_new_session_argv()
        pairs = self._env_pairs(argv)
        assert pairs.get("CLAUDE_STATUS_AUQ_MODE") == "record"

    def test_waggle_owned_label_1(self):
        argv = self._run_and_get_new_session_argv()
        pairs = self._env_pairs(argv)
        assert pairs.get("CLAUDE_STATUS_LABEL_WAGGLE_OWNED") == "1"

    def test_waggle_session_name_label(self):
        argv = self._run_and_get_new_session_argv(sn="test-sess")
        pairs = self._env_pairs(argv)
        assert pairs.get("CLAUDE_STATUS_LABEL_WAGGLE_SESSION_NAME") == "test-sess"

    def test_waggle_model_label_lowercased(self):
        argv = self._run_and_get_new_session_argv(model="Claude-Sonnet-4-5")
        pairs = self._env_pairs(argv)
        assert pairs.get("CLAUDE_STATUS_LABEL_WAGGLE_MODEL") == "claude-sonnet-4-5"

    def test_waggle_repo_label(self):
        argv = self._run_and_get_new_session_argv(repo="/srv/myrepo")
        pairs = self._env_pairs(argv)
        assert pairs.get("CLAUDE_STATUS_LABEL_WAGGLE_REPO") == "/srv/myrepo"

    def test_all_seven_env_vars_present(self):
        argv = self._run_and_get_new_session_argv()
        pairs = self._env_pairs(argv)
        for key in sp._REQUIRED_ENV_VARS:
            assert key in pairs, f"missing required env var {key!r}"


# ---------------------------------------------------------------------------
# Claude launch command — window 0, pane 0
# ---------------------------------------------------------------------------


class TestSpawnWorkerLaunch:
    def test_send_keys_is_second_call(self):
        calls, patcher = _patch_tmux([_OK_TRIPLE, _OK_TRIPLE])
        try:
            sp.spawn_worker_impl("sonnet", "/tmp/repo", session_name="s1")
        finally:
            patcher.stop()
        assert calls[1][0] == "send-keys"

    def test_send_keys_targets_window_0_pane_0(self):
        calls, patcher = _patch_tmux([_OK_TRIPLE, _OK_TRIPLE])
        try:
            sp.spawn_worker_impl("sonnet", "/tmp/repo", session_name="s1")
        finally:
            patcher.stop()
        argv = calls[1]
        assert "-t" in argv
        idx = argv.index("-t")
        target = argv[idx + 1]
        assert target == "s1:0.0"

    def test_send_keys_sends_claude_model_command(self):
        calls, patcher = _patch_tmux([_OK_TRIPLE, _OK_TRIPLE])
        try:
            sp.spawn_worker_impl("Claude-Opus", "/tmp/repo", session_name="s1")
        finally:
            patcher.stop()
        argv = calls[1]
        # The command string should be in argv (before "Enter")
        cmd_parts = " ".join(argv)
        assert "claude --model claude-opus" in cmd_parts

    def test_send_keys_includes_enter(self):
        calls, patcher = _patch_tmux([_OK_TRIPLE, _OK_TRIPLE])
        try:
            sp.spawn_worker_impl("sonnet", "/tmp/repo", session_name="s1")
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
            result = sp.spawn_worker_impl("sonnet", "/tmp/repo")
        finally:
            patcher.stop()
        assert result.get("ok") is False
        assert result.get("err_name") == "ErrTmuxSessionCreate"

    def test_send_keys_failure_returns_operation_failed(self):
        calls, patcher = _patch_tmux([_OK_TRIPLE, ("", "no such session", 1)])
        try:
            result = sp.spawn_worker_impl("sonnet", "/tmp/repo")
        finally:
            patcher.stop()
        assert result.get("ok") is False
        assert result.get("err_name") == "ErrTmuxSendKeys"

    def test_exactly_two_tmux_calls_on_success(self):
        calls, patcher = _patch_tmux([_OK_TRIPLE, _OK_TRIPLE])
        try:
            sp.spawn_worker_impl("sonnet", "/tmp/repo")
        finally:
            patcher.stop()
        assert len(calls) == 2

    def test_one_tmux_call_on_new_session_failure(self):
        calls, patcher = _patch_tmux([("", "err", 1)])
        try:
            sp.spawn_worker_impl("sonnet", "/tmp/repo")
        finally:
            patcher.stop()
        assert len(calls) == 1
