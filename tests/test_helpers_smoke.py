"""Smoke tests guarding helpers.py import and shape invariants.

Imports only from tests.helpers and tests.sample_payloads.
No claude_spawn.* production imports.
"""

import pytest

import tests.sample_payloads  # noqa: F401 — verify importable without error
from tests.helpers import (
    _FakeClaudeStatus,
    fake_claude_status,
    fake_tmux_pane,
    fake_worker_record,
    fake_workers_response,
)

# ---------------------------------------------------------------------------
# fake_worker_record
# ---------------------------------------------------------------------------


def test_fake_worker_record_basic_shape():
    r = fake_worker_record("inst-abc", "waiting")
    assert r["instance_id"] == "inst-abc"
    assert r["status"] == "waiting"
    assert isinstance(r["labels"], dict)
    assert r["pending"] is None


def test_fake_worker_record_default_labels_keys():
    r = fake_worker_record("inst-abc", "waiting")
    for key in ("claude_spawn_owned", "claude_spawn_session_name", "claude_spawn_model", "claude_spawn_repo"):
        assert key in r["labels"], f"default labels missing {key!r}"


def test_fake_worker_record_pending_roundtrip():
    pending = {"kind": "ask_user_question", "request_id": 7, "tool_input": {"questions": []}}
    r = fake_worker_record("inst-xyz", "ask_user", pending=pending)
    assert r["pending"]["kind"] == "ask_user_question"


def test_fake_worker_record_custom_labels():
    custom = {"owner": "test"}
    r = fake_worker_record("inst-lmn", "working", labels=custom)
    assert r["labels"] == {"owner": "test"}


# ---------------------------------------------------------------------------
# fake_workers_response
# ---------------------------------------------------------------------------


def test_fake_workers_response_two_records():
    r1 = fake_worker_record("a", "working")
    r2 = fake_worker_record("b", "waiting")
    result = fake_workers_response([r1, r2])
    assert result == {"workers": [r1, r2], "skipped": []}


def test_fake_workers_response_with_skipped():
    result = fake_workers_response([], skipped=("err-row",))
    assert result["workers"] == []
    assert len(result["skipped"]) == 1


def test_fake_workers_response_empty():
    result = fake_workers_response([])
    assert result == {"workers": [], "skipped": []}


# ---------------------------------------------------------------------------
# fake_tmux_pane
# ---------------------------------------------------------------------------


def test_fake_tmux_pane_capture_pane_returns_list():
    pane = fake_tmux_pane("line one\nline two")
    lines = pane.capture_pane()
    assert isinstance(lines, list)


def test_fake_tmux_pane_text_roundtrip():
    pane = fake_tmux_pane("line one\nline two")
    lines = pane.capture_pane()
    assert "\n".join(lines) == "line one\nline two"


def test_fake_tmux_pane_single_line():
    pane = fake_tmux_pane("hello world")
    lines = pane.capture_pane()
    assert lines == ["hello world"]


# ---------------------------------------------------------------------------
# fake_claude_status — test internal mechanics without touching claude_spawn.*
# ---------------------------------------------------------------------------


def test_fake_claude_status_importable():
    assert callable(fake_claude_status)


def test_fake_claude_status_calls_start_empty():
    fcs = _FakeClaudeStatus([("out", "", 0)])
    assert fcs.calls == []


def test_fake_claude_status_side_effect_returns_triple():
    fcs = _FakeClaudeStatus([("stdout-data", "err-data", 1)])
    result = fcs._side_effect(["workers"])
    assert result == ("stdout-data", "err-data", 1)
    assert fcs.calls == [["workers"]]


def test_fake_claude_status_overrun_raises():
    fcs = _FakeClaudeStatus([("out", "", 0)])
    fcs._side_effect(["workers"])  # consume the one triple
    with pytest.raises(AssertionError, match="fake_claude_status"):
        fcs._side_effect(["worker", "x"])  # overrun


def test_fake_claude_status_unconsumed_raises_on_clean_exit():
    fcs = _FakeClaudeStatus([("out", "", 0), ("out2", "", 0)])
    # Consume only the first
    fcs._side_effect(["workers"])
    # __exit__ with no exception — should raise because one triple is un-consumed
    with pytest.raises(AssertionError, match="un-consumed"):
        fcs.__exit__(None, None, None)


def test_fake_claude_status_unconsumed_silent_on_exc_exit():
    # If exiting due to an exception, __exit__ should not mask it with a second assertion
    fcs = _FakeClaudeStatus([("out", "", 0)])
    # Consume nothing; exit with an active exception — should return False (not raise)
    result = fcs.__exit__(ValueError, ValueError("test"), None)
    assert result is False


def test_fake_claude_status_records_multiple_calls():
    fcs = _FakeClaudeStatus([
        ("out1", "", 0),
        ("out2", "err", 1),
    ])
    fcs._side_effect(["workers", "--label", "claude_spawn_owned=1"])
    fcs._side_effect(["worker", "inst-abc"])
    assert fcs.calls[0] == ["workers", "--label", "claude_spawn_owned=1"]
    assert fcs.calls[1] == ["worker", "inst-abc"]
