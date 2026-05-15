"""Unit tests for waggle.spawn.send_input_impl (SR-3.4).

Tests that text is typed verbatim (no implicit Enter) to window 0, pane 0.
All tmux calls go through the waggle.spawn._tmux seam.  No conftest.py.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

import waggle.spawn as sp

_OK = ("", "", 0)
_FAIL = ("", "no such session", 1)


def _patch_tmux(triples):
    queue = list(triples)
    calls = []

    def side_effect(argv):
        calls.append(list(argv))
        if not queue:
            raise AssertionError(f"_tmux called unexpectedly: argv={argv!r}")
        return queue.pop(0)

    patcher = patch("waggle.spawn._tmux", side_effect=side_effect)
    patcher.start()
    return calls, patcher


class TestSendInputVerb:
    def test_send_keys_subcommand(self):
        calls, p = _patch_tmux([_OK])
        try:
            sp.send_input_impl("my-session", "hello world")
        finally:
            p.stop()
        assert calls[0][0] == "send-keys"

    def test_targets_window_0_pane_0(self):
        calls, p = _patch_tmux([_OK])
        try:
            sp.send_input_impl("my-session", "hello")
        finally:
            p.stop()
        argv = calls[0]
        idx = argv.index("-t")
        assert argv[idx + 1] == "my-session:0.0"

    def test_text_sent_verbatim(self):
        calls, p = _patch_tmux([_OK])
        try:
            sp.send_input_impl("my-session", "verbatim text")
        finally:
            p.stop()
        assert "verbatim text" in calls[0]

    def test_no_implicit_enter(self):
        """Enter must NOT be appended to the text."""
        calls, p = _patch_tmux([_OK])
        try:
            sp.send_input_impl("my-session", "no enter please")
        finally:
            p.stop()
        assert "Enter" not in calls[0]

    def test_exactly_one_tmux_call(self):
        calls, p = _patch_tmux([_OK])
        try:
            sp.send_input_impl("my-session", "hi")
        finally:
            p.stop()
        assert len(calls) == 1

    def test_success_returns_ok_true(self):
        calls, p = _patch_tmux([_OK])
        try:
            result = sp.send_input_impl("my-session", "hi")
        finally:
            p.stop()
        assert result["ok"] is True
        assert result["operation"] == "send_input"

    def test_tmux_failure_returns_operation_failed(self):
        calls, p = _patch_tmux([_FAIL])
        try:
            result = sp.send_input_impl("my-session", "hi")
        finally:
            p.stop()
        assert result["ok"] is False
        assert result["err_name"] == "ErrTmuxSendKeys"

    def test_empty_text_sent_as_is(self):
        calls, p = _patch_tmux([_OK])
        try:
            sp.send_input_impl("my-session", "")
        finally:
            p.stop()
        assert "" in calls[0]
