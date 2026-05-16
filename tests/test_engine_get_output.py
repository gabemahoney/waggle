"""Unit tests for claude_spawn.spawn.get_output_impl (SR-3.4).

Tests window 0/pane 0 targeting, default scrollback, out-of-range refusal,
and raw-text passthrough.  All tmux calls go through claude_spawn.spawn._tmux.
No conftest.py.
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


_PANE_TEXT = "line one\nline two\nline three\n"
_OK = (_PANE_TEXT, "", 0)
_FAIL = ("", "no such session", 1)


class TestGetOutputTargeting:
    def test_capture_pane_subcommand(self):
        calls, p = _patch_tmux([_OK])
        try:
            sp.get_output_impl("my-sess")
        finally:
            p.stop()
        assert calls[0][0] == "capture-pane"

    def test_targets_window_0_pane_0(self):
        calls, p = _patch_tmux([_OK])
        try:
            sp.get_output_impl("my-sess")
        finally:
            p.stop()
        argv = calls[0]
        idx = argv.index("-t")
        assert argv[idx + 1] == "my-sess:0.0"

    def test_print_flag_present(self):
        calls, p = _patch_tmux([_OK])
        try:
            sp.get_output_impl("my-sess")
        finally:
            p.stop()
        assert "-p" in calls[0]

    def test_exactly_one_tmux_call(self):
        calls, p = _patch_tmux([_OK])
        try:
            sp.get_output_impl("my-sess")
        finally:
            p.stop()
        assert len(calls) == 1


class TestGetOutputScrollback:
    def _get_scrollback_arg(self, calls):
        argv = calls[0]
        idx = argv.index("-S")
        return argv[idx + 1]

    def test_default_scrollback_is_50(self):
        calls, p = _patch_tmux([_OK])
        try:
            sp.get_output_impl("my-sess")
        finally:
            p.stop()
        assert self._get_scrollback_arg(calls) == "-50"

    def test_explicit_scrollback_used(self):
        calls, p = _patch_tmux([_OK])
        try:
            sp.get_output_impl("my-sess", scrollback=100)
        finally:
            p.stop()
        assert self._get_scrollback_arg(calls) == "-100"

    def test_scrollback_1_accepted(self):
        calls, p = _patch_tmux([_OK])
        try:
            result = sp.get_output_impl("my-sess", scrollback=1)
        finally:
            p.stop()
        assert result["ok"] is True

    def test_scrollback_1000_accepted(self):
        calls, p = _patch_tmux([_OK])
        try:
            result = sp.get_output_impl("my-sess", scrollback=1000)
        finally:
            p.stop()
        assert result["ok"] is True

    def test_scrollback_0_refused(self):
        calls, p = _patch_tmux([])
        try:
            result = sp.get_output_impl("my-sess", scrollback=0)
        finally:
            p.stop()
        assert result["ok"] is False
        assert result["err_name"] == "ErrScrollbackOutOfRange"
        assert len(calls) == 0  # no tmux call made

    def test_scrollback_1001_refused(self):
        calls, p = _patch_tmux([])
        try:
            result = sp.get_output_impl("my-sess", scrollback=1001)
        finally:
            p.stop()
        assert result["ok"] is False
        assert result["err_name"] == "ErrScrollbackOutOfRange"

    @pytest.mark.parametrize("bad", [-1, 0, 1001, 9999])
    def test_out_of_range_refused(self, bad):
        calls, p = _patch_tmux([])
        try:
            result = sp.get_output_impl("my-sess", scrollback=bad)
        finally:
            p.stop()
        assert result["ok"] is False
        assert result["err_name"] == "ErrScrollbackOutOfRange"


class TestGetOutputContent:
    def test_raw_text_returned_unmodified(self):
        raw = "raw output line 1\nraw output line 2\n"
        calls, p = _patch_tmux([(raw, "", 0)])
        try:
            result = sp.get_output_impl("my-sess")
        finally:
            p.stop()
        assert result["ok"] is True
        assert result["content"] == raw

    def test_tmux_failure_returns_operation_failed(self):
        calls, p = _patch_tmux([_FAIL])
        try:
            result = sp.get_output_impl("my-sess")
        finally:
            p.stop()
        assert result["ok"] is False
        assert result["err_name"] == "ErrTmuxCaptureFailed"
