"""Unit tests for waggle.spawn.terminate_worker_impl (SR-3.4).

Tests that the correct session name is passed to kill-session and that an
absent session returns operation-failed.  No conftest.py.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

import claude_spawn.spawn as sp


def _patch_tmux(triples):
    queue = list(triples)
    calls = []

    def side_effect(argv):
        calls.append(list(argv))
        if not queue:
            raise AssertionError(f"_tmux called unexpectedly: argv={argv!r}")
        return queue.pop(0)

    patcher = patch("claude_spawn.spawn._tmux", side_effect=side_effect)
    patcher.start()
    return calls, patcher


_OK = ("", "", 0)
_FAIL = ("", "session not found", 1)


class TestTerminateWorker:
    def test_kill_session_subcommand(self):
        calls, p = _patch_tmux([_OK])
        try:
            sp.terminate_worker_impl("my-session")
        finally:
            p.stop()
        assert calls[0][0] == "kill-session"

    def test_target_flag_present(self):
        calls, p = _patch_tmux([_OK])
        try:
            sp.terminate_worker_impl("my-session")
        finally:
            p.stop()
        argv = calls[0]
        assert "-t" in argv
        idx = argv.index("-t")
        assert argv[idx + 1] == "my-session"

    def test_exactly_one_tmux_call(self):
        calls, p = _patch_tmux([_OK])
        try:
            sp.terminate_worker_impl("my-session")
        finally:
            p.stop()
        assert len(calls) == 1

    def test_success_returns_ok_true(self):
        calls, p = _patch_tmux([_OK])
        try:
            result = sp.terminate_worker_impl("my-session")
        finally:
            p.stop()
        assert result["ok"] is True
        assert result["operation"] == "terminate_worker"

    def test_absent_session_returns_operation_failed(self):
        calls, p = _patch_tmux([_FAIL])
        try:
            result = sp.terminate_worker_impl("nonexistent-session")
        finally:
            p.stop()
        assert result["ok"] is False
        assert result["err_name"] == "ErrTmuxKillFailed"

    def test_different_session_names(self):
        for name in ["waggle-abc12345", "my-worker", "session-1"]:
            calls, p = _patch_tmux([_OK])
            try:
                sp.terminate_worker_impl(name)
            finally:
                p.stop()
            idx = calls[0].index("-t")
            assert calls[0][idx + 1] == name
