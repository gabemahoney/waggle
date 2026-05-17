"""Tests for spawn_worker_impl readiness polling loop (SR-5, SR-5.3, SR-5.4, SR-10.1).

Four cases:
1. Happy path — worker registers on second poll.
2. Timeout path — kill-session called, ErrSpawnReadinessTimeout returned.
3. Best-effort kill on timeout — kill-session fails; err_name unchanged.
4. Worker-exited-early — has-session probe returns non-zero; ErrSpawnWorkerExitedEarly returned.

All tests complete well under 1 second of wall time.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import claude_spawn.spawn as sp
from tests.helpers import (
    fake_claude_status,
    fake_worker_record,
    fake_workers_response,
)

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_OK = ("", "", 0)


def _empty_workers_triple() -> tuple[str, str, int]:
    """Success triple: empty workers list."""
    return (json.dumps({"workers": [], "skipped": []}), "", 0)


def _workers_triple_with(records: list[dict]) -> tuple[str, str, int]:
    """Success triple: non-empty workers list."""
    return (json.dumps(fake_workers_response(records)), "", 0)


def _make_tmux_recorder(responses: list[tuple[str, str, int]] | None = None):
    """Return (calls_list, side_effect_fn).

    ``responses`` is consumed in order.  If *responses* is None, every call
    returns ``("", "", 0)``.  Pass a list to exercise different return codes
    per invocation.
    """
    calls: list[list[str]] = []
    queue = list(responses) if responses is not None else None

    def side_effect(argv: list[str]) -> tuple[str, str, int]:
        calls.append(list(argv))
        if queue is not None:
            if not queue:
                raise AssertionError(
                    f"_tmux called more times than expected; argv={argv!r}"
                )
            return queue.pop(0)
        return ("", "", 0)

    return calls, side_effect


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------


class TestSpawnWorkerReadiness:
    # ------------------------------------------------------------------
    # Case 1: happy path — worker registers on second poll
    # ------------------------------------------------------------------

    def test_happy_path_worker_registers_on_second_poll(self):
        """Worker appears in the second readiness poll; return is a 2-key success dict."""
        _IID = "known-uuid-0000-4000-8000-000000000001"
        _SESS = "readiness-happy-sess"

        rec = fake_worker_record(instance_id=_IID, status="working", cwd="/tmp")

        # Triple layout:
        #   [0] precheck:       empty workers (no collision)
        #   [1] readiness poll 1: empty workers (not yet registered)
        #   [2] readiness poll 2: worker present → function returns
        cs_triples = [
            _empty_workers_triple(),
            _empty_workers_triple(),
            _workers_triple_with([rec]),
        ]

        # _tmux layout:
        #   [0] new-session → OK
        #   [1] send-keys   → OK
        #   [2] has-session (after poll 1 found nothing) → OK (still alive)
        tmux_calls, tmux_side = _make_tmux_recorder([_OK, _OK, _OK])

        with patch("claude_spawn.spawn._SPAWN_READINESS_TIMEOUT", 1.0):
            with patch("claude_spawn.spawn._tmux", side_effect=tmux_side):
                with fake_claude_status(cs_triples):
                    result = sp.spawn_worker_impl(
                        cwd="/tmp",
                        instance_id=_IID,
                        tmux_session_name=_SESS,
                    )

        # Return shape: exactly 2 keys, no "ok" key
        assert set(result.keys()) == {"instance_id", "tmux_session_name"}, (
            f"unexpected keys in success result: {set(result.keys())!r}"
        )
        assert result["instance_id"] == _IID
        assert result["tmux_session_name"] == _SESS

        # No kill-session
        kill_calls = [c for c in tmux_calls if c and c[0] == "kill-session"]
        assert not kill_calls, f"unexpected kill-session call(s): {kill_calls}"

        # Poll loop ran ≥1 and ≤2 iterations.
        # The fake_claude_status context verifies all 3 triples were consumed
        # (precheck + 2 readiness polls), confirming exactly 2 polls ran.
        # Additionally, exactly 1 has-session probe must appear.
        hs_calls = [c for c in tmux_calls if c and c[0] == "has-session"]
        assert 1 <= len(hs_calls) <= 2, (
            f"expected 1–2 has-session calls, got {len(hs_calls)}: {hs_calls}"
        )

    # ------------------------------------------------------------------
    # Case 2: timeout path
    # ------------------------------------------------------------------

    def test_timeout_path(self):
        """Timeout: kill-session called; ErrSpawnReadinessTimeout returned.

        With _SPAWN_READINESS_TIMEOUT=0.0 the deadline is already past when
        the while-loop condition is first evaluated, so 0 readiness polls run.
        Only the precheck CS call happens; kill-session is the final _tmux call.
        """
        _IID = "timeout-test-0000-4000-8000-000000000002"
        _SESS = "readiness-timeout-sess"

        # 0.0s timeout → loop never runs → only precheck triple consumed
        cs_triples = [_empty_workers_triple()]

        tmux_calls, tmux_side = _make_tmux_recorder()  # always returns OK

        with patch("claude_spawn.spawn._SPAWN_READINESS_TIMEOUT", 0.0):
            with patch("claude_spawn.spawn._tmux", side_effect=tmux_side):
                with fake_claude_status(cs_triples):
                    result = sp.spawn_worker_impl(
                        cwd="/tmp",
                        instance_id=_IID,
                        tmux_session_name=_SESS,
                    )

        assert result.get("ok") is False
        assert result.get("err_name") == "ErrSpawnReadinessTimeout"

        desc = result.get("err_description", "")
        assert _SESS in desc, (
            f"err_description must contain tmux_session_name {_SESS!r}: {desc!r}"
        )
        # Timeout value "0.0" appears in "...within 0.0s"
        assert "0.0" in desc, (
            f"err_description must contain patched timeout value '0.0': {desc!r}"
        )

        # kill-session must have been called with the session name
        kill_calls = [c for c in tmux_calls if c and c[0] == "kill-session"]
        assert len(kill_calls) == 1, (
            f"expected exactly 1 kill-session call, got {kill_calls}"
        )
        assert _SESS in " ".join(kill_calls[0]), (
            f"kill-session must target {_SESS!r}, got {kill_calls[0]}"
        )

    # ------------------------------------------------------------------
    # Case 3: best-effort kill on timeout
    # ------------------------------------------------------------------

    def test_best_effort_kill_on_timeout(self):
        """Kill-session returns non-zero; err_name must remain ErrSpawnReadinessTimeout."""
        _IID = "kill-fail-test-4000-8000-000000000003"
        _SESS = "readiness-kill-fail-sess"

        def tmux_side(argv: list[str]) -> tuple[str, str, int]:
            if argv and argv[0] == "kill-session":
                return ("", "kill failed: no such session", 1)
            return ("", "", 0)

        cs_triples = [_empty_workers_triple()]

        with patch("claude_spawn.spawn._SPAWN_READINESS_TIMEOUT", 0.0):
            with patch("claude_spawn.spawn._tmux", side_effect=tmux_side):
                with fake_claude_status(cs_triples):
                    result = sp.spawn_worker_impl(
                        cwd="/tmp",
                        instance_id=_IID,
                        tmux_session_name=_SESS,
                    )

        # Kill failure must NOT change the error surface
        assert result.get("ok") is False
        assert result.get("err_name") == "ErrSpawnReadinessTimeout", (
            f"kill failure must not change err_name; got {result.get('err_name')!r}"
        )

    # ------------------------------------------------------------------
    # Case 4: worker-exited-early
    # ------------------------------------------------------------------

    def test_worker_exited_early(self):
        """has-session returns non-zero; ErrSpawnWorkerExitedEarly with captured pane text."""
        _IID = "early-exit-test-4000-8000-000000000004"
        _SESS = "readiness-early-exit-sess"

        # _tmux responses (by call order):
        #   0: new-session → OK
        #   1: send-keys   → OK
        #   2: has-session → non-zero (session gone after first empty poll)
        #   3: capture-pane → success with pane text
        tmux_responses = [
            ("", "", 0),                             # new-session
            ("", "", 0),                             # send-keys
            ("", "no such session", 1),              # has-session: gone
            ("FATAL: something bad\n", "", 0),       # capture-pane: success
        ]
        tmux_calls, tmux_side = _make_tmux_recorder(tmux_responses)

        # CS triples:
        #   [0] precheck:         empty (no collision)
        #   [1] readiness poll 1: empty (not found → fall through to has-session)
        cs_triples = [
            _empty_workers_triple(),
            _empty_workers_triple(),
        ]

        with patch("claude_spawn.spawn._SPAWN_READINESS_TIMEOUT", 1.0):
            with patch("claude_spawn.spawn._tmux", side_effect=tmux_side):
                with fake_claude_status(cs_triples):
                    result = sp.spawn_worker_impl(
                        cwd="/tmp",
                        instance_id=_IID,
                        tmux_session_name=_SESS,
                    )

        assert result.get("ok") is False
        assert result.get("err_name") == "ErrSpawnWorkerExitedEarly"

        desc = result.get("err_description", "")
        assert "FATAL: something bad" in desc, (
            f"err_description must contain captured pane text: {desc!r}"
        )

        # capture-pane must appear in the recorded _tmux calls
        cap_calls = [c for c in tmux_calls if c and c[0] == "capture-pane"]
        assert len(cap_calls) >= 1, (
            f"expected at least one capture-pane call, got: {tmux_calls}"
        )
