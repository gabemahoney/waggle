"""Unit tests for waggle.spawn.answer_question_impl (SR-3.5).

Covers: happy path, multi-question refusal, no-match refusal,
question-not-visible refusal, whitespace normalization, Enter in send-keys.
Uses fake_claude_status and waggle.spawn._tmux seam.  No conftest.py.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

import claude_spawn.spawn as sp
from tests.helpers import (
    fake_claude_status,
    fake_worker_record,
    fake_workers_response,
)
from tests.sample_payloads import (
    PENDING_ASK_USER_MULTI,
    PENDING_ASK_USER_SINGLE,
    STDERR_ERR_STORE_UNAVAILABLE,
    WORKER_ASK_USER_SINGLE,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_worker_with_pending(instance_id, request_id, questions, session_name="worker-sess"):
    """Return a worker record with a custom pending ask_user_question."""
    pending = {
        "kind": "ask_user_question",
        "request_id": request_id,
        "tool_name": "AskUserQuestion",
        "tool_input": {"questions": questions},
    }
    labels = {
        "waggle_owned": "1",
        "waggle_session_name": session_name,
        "waggle_model": "claude-sonnet-4-5",
        "waggle_repo": "/work",
    }
    return fake_worker_record(instance_id, "ask_user", labels=labels, pending=pending)


_QUESTION_TEXT = "Should I proceed with the refactor?"
_SINGLE_Q = [{"question": _QUESTION_TEXT, "options": None, "multiSelect": False}]
_MULTI_Q = [
    {"question": "Q1?", "options": None, "multiSelect": False},
    {"question": "Q2?", "options": None, "multiSelect": False},
]

_PANE_WITH_QUESTION = f"Some pane content\n{_QUESTION_TEXT}\n> "
_PANE_WITHOUT_QUESTION = "Some other pane content\nNo question here\n"
_OK_TMUX = ("", "", 0)
_FAIL_TMUX = ("", "tmux error", 1)


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


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestAnswerQuestionHappyPath:
    def test_success_returns_ok_true(self):
        worker = _make_worker_with_pending("inst-abc", 7, _SINGLE_Q)
        cs_payload = json.dumps(fake_workers_response([worker]))
        tmux_calls, p = _patch_tmux([
            (_PANE_WITH_QUESTION, "", 0),  # capture-pane
            _OK_TMUX,                        # send-keys
        ])
        try:
            with fake_claude_status([(cs_payload, "", 0)]):
                result = sp.answer_question_impl(7, "yes")
        finally:
            p.stop()
        assert result["ok"] is True
        assert result["operation"] == "answer_question"

    def test_enter_sent_in_same_send_keys_call(self):
        worker = _make_worker_with_pending("inst-abc", 7, _SINGLE_Q)
        cs_payload = json.dumps(fake_workers_response([worker]))
        tmux_calls, p = _patch_tmux([
            (_PANE_WITH_QUESTION, "", 0),
            _OK_TMUX,
        ])
        try:
            with fake_claude_status([(cs_payload, "", 0)]):
                sp.answer_question_impl(7, "yes")
        finally:
            p.stop()
        send_keys_argv = tmux_calls[1]
        assert "Enter" in send_keys_argv
        assert "yes" in send_keys_argv

    def test_answer_and_enter_in_same_call_not_separate(self):
        """Verify send-keys is called exactly once (answer + Enter together)."""
        worker = _make_worker_with_pending("inst-abc", 7, _SINGLE_Q)
        cs_payload = json.dumps(fake_workers_response([worker]))
        tmux_calls, p = _patch_tmux([
            (_PANE_WITH_QUESTION, "", 0),
            _OK_TMUX,
        ])
        try:
            with fake_claude_status([(cs_payload, "", 0)]):
                sp.answer_question_impl(7, "yes")
        finally:
            p.stop()
        # Only one send-keys call (not two)
        send_keys_calls = [c for c in tmux_calls if c[0] == "send-keys"]
        assert len(send_keys_calls) == 1

    def test_capture_pane_targets_session_window_0_pane_0(self):
        worker = _make_worker_with_pending("inst-abc", 7, _SINGLE_Q, session_name="my-sess")
        cs_payload = json.dumps(fake_workers_response([worker]))
        tmux_calls, p = _patch_tmux([
            (_PANE_WITH_QUESTION, "", 0),
            _OK_TMUX,
        ])
        try:
            with fake_claude_status([(cs_payload, "", 0)]):
                sp.answer_question_impl(7, "yes")
        finally:
            p.stop()
        capture_argv = tmux_calls[0]
        assert capture_argv[0] == "capture-pane"
        idx = capture_argv.index("-t")
        assert capture_argv[idx + 1] == "my-sess:0.0"

    def test_send_keys_targets_correct_session(self):
        worker = _make_worker_with_pending("inst-abc", 7, _SINGLE_Q, session_name="my-sess")
        cs_payload = json.dumps(fake_workers_response([worker]))
        tmux_calls, p = _patch_tmux([
            (_PANE_WITH_QUESTION, "", 0),
            _OK_TMUX,
        ])
        try:
            with fake_claude_status([(cs_payload, "", 0)]):
                sp.answer_question_impl(7, "yes")
        finally:
            p.stop()
        send_argv = tmux_calls[1]
        idx = send_argv.index("-t")
        assert send_argv[idx + 1] == "my-sess:0.0"


# ---------------------------------------------------------------------------
# Multi-question refusal
# ---------------------------------------------------------------------------


class TestAnswerQuestionMultiQuestion:
    def test_multi_question_refused(self):
        worker = _make_worker_with_pending("inst-abc", 7, _MULTI_Q)
        cs_payload = json.dumps(fake_workers_response([worker]))
        tmux_calls, p = _patch_tmux([])
        try:
            with fake_claude_status([(cs_payload, "", 0)]):
                result = sp.answer_question_impl(7, "1")
        finally:
            p.stop()
        assert result["ok"] is False
        assert result["err_name"] == "ErrMultiQuestionUnsupported"

    def test_multi_question_no_tmux_calls(self):
        worker = _make_worker_with_pending("inst-abc", 7, _MULTI_Q)
        cs_payload = json.dumps(fake_workers_response([worker]))
        tmux_calls, p = _patch_tmux([])
        try:
            with fake_claude_status([(cs_payload, "", 0)]):
                sp.answer_question_impl(7, "1")
        finally:
            p.stop()
        assert len(tmux_calls) == 0  # no tmux calls before refusal


# ---------------------------------------------------------------------------
# No matching request_id
# ---------------------------------------------------------------------------


class TestAnswerQuestionNoMatch:
    def test_no_match_returns_operation_failed(self):
        worker = _make_worker_with_pending("inst-abc", 5, _SINGLE_Q)
        cs_payload = json.dumps(fake_workers_response([worker]))
        tmux_calls, p = _patch_tmux([])
        try:
            with fake_claude_status([(cs_payload, "", 0)]):
                result = sp.answer_question_impl(999, "yes")  # wrong ID
        finally:
            p.stop()
        assert result["ok"] is False
        assert result["err_name"] == "ErrNoPendingAskUserQuestion"

    def test_empty_workers_returns_operation_failed(self):
        cs_payload = json.dumps(fake_workers_response([]))
        tmux_calls, p = _patch_tmux([])
        try:
            with fake_claude_status([(cs_payload, "", 0)]):
                result = sp.answer_question_impl(7, "yes")
        finally:
            p.stop()
        assert result["ok"] is False
        assert result["err_name"] == "ErrNoPendingAskUserQuestion"


# ---------------------------------------------------------------------------
# Question not visible in pane (ErrQuestionNoLongerVisible)
# ---------------------------------------------------------------------------


class TestAnswerQuestionNotVisible:
    def test_question_absent_from_pane_refused(self):
        worker = _make_worker_with_pending("inst-abc", 7, _SINGLE_Q)
        cs_payload = json.dumps(fake_workers_response([worker]))
        tmux_calls, p = _patch_tmux([
            (_PANE_WITHOUT_QUESTION, "", 0),  # pane doesn't have question
        ])
        try:
            with fake_claude_status([(cs_payload, "", 0)]):
                result = sp.answer_question_impl(7, "yes")
        finally:
            p.stop()
        assert result["ok"] is False
        assert result["err_name"] == "ErrQuestionNoLongerVisible"

    def test_no_send_keys_when_not_visible(self):
        worker = _make_worker_with_pending("inst-abc", 7, _SINGLE_Q)
        cs_payload = json.dumps(fake_workers_response([worker]))
        tmux_calls, p = _patch_tmux([
            (_PANE_WITHOUT_QUESTION, "", 0),
        ])
        try:
            with fake_claude_status([(cs_payload, "", 0)]):
                sp.answer_question_impl(7, "yes")
        finally:
            p.stop()
        send_keys_calls = [c for c in tmux_calls if c[0] == "send-keys"]
        assert len(send_keys_calls) == 0


# ---------------------------------------------------------------------------
# Whitespace normalization
# ---------------------------------------------------------------------------


class TestAnswerQuestionWhitespaceNorm:
    def test_line_wrapped_question_still_matches(self):
        """Question split across pane lines (with extra whitespace) should match."""
        question = "Should I proceed with the refactor?"
        # Simulate narrow terminal: question wrapped with a newline in the middle
        wrapped_pane = "Some pane content\nShould I proceed\nwith the refactor?\n> "
        single_q = [{"question": question, "options": None, "multiSelect": False}]

        worker = _make_worker_with_pending("inst-abc", 7, single_q)
        cs_payload = json.dumps(fake_workers_response([worker]))
        tmux_calls, p = _patch_tmux([
            (wrapped_pane, "", 0),
            _OK_TMUX,
        ])
        try:
            with fake_claude_status([(cs_payload, "", 0)]):
                result = sp.answer_question_impl(7, "yes")
        finally:
            p.stop()
        assert result["ok"] is True

    def test_extra_spaces_in_pane_still_match(self):
        question = "Is this correct?"
        pane = "Is   this   correct?\n> "
        single_q = [{"question": question, "options": None, "multiSelect": False}]

        worker = _make_worker_with_pending("inst-abc", 7, single_q)
        cs_payload = json.dumps(fake_workers_response([worker]))
        tmux_calls, p = _patch_tmux([
            (pane, "", 0),
            _OK_TMUX,
        ])
        try:
            with fake_claude_status([(cs_payload, "", 0)]):
                result = sp.answer_question_impl(7, "yes")
        finally:
            p.stop()
        assert result["ok"] is True


# ---------------------------------------------------------------------------
# Claude Status failure propagation
# ---------------------------------------------------------------------------


class TestAnswerQuestionCSError:
    def test_cs_error_propagates_to_caller(self):
        tmux_calls, p = _patch_tmux([])
        try:
            with fake_claude_status([("", STDERR_ERR_STORE_UNAVAILABLE, 1)]):
                result = sp.answer_question_impl(7, "yes")
        finally:
            p.stop()
        assert result["ok"] is False
        assert result["err_name"] == "ErrStoreUnavailable"
        assert len(tmux_calls) == 0
