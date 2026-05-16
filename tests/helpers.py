"""Shared test helpers for the Waggle test suite (SR-11.2).

No conftest.py — helpers live in this plain importable module.
No imports from claude_spawn.* production source except via the patch target.
"""

from __future__ import annotations

import contextlib
from collections.abc import Sequence
from typing import Any
from unittest.mock import patch

# ---------------------------------------------------------------------------
# fake_claude_status — patches claude_spawn.claude_status._run
# ---------------------------------------------------------------------------

_SEAM = "claude_spawn.claude_status._run"


class _FakeClaudeStatus:
    """Context-manager that replaces the claude-status subprocess seam.

    Usage::

        with fake_claude_status([
            (stdout1, stderr1, exit_code1),
            (stdout2, stderr2, exit_code2),
        ]) as fcs:
            # production code calls claude_spawn.claude_status._run(argv)
            assert fcs.calls[0] == ["workers", "--label", "claude_spawn_owned=1"]

    Recorded invocations are in ``fcs.calls`` as a list of argv lists.
    Raises ``AssertionError`` if:
    - the seam is called more times than canned triples were provided, or
    - the context exits with un-consumed triples remaining.
    """

    def __init__(self, triples: Sequence[tuple[str, str, int]]) -> None:
        self._triples: list[tuple[str, str, int]] = list(triples)
        self._remaining: list[tuple[str, str, int]] = list(triples)
        self.calls: list[list[str]] = []
        self._patcher: Any = None

    def _side_effect(self, argv: list[str]) -> tuple[str, str, int]:
        self.calls.append(list(argv))
        if not self._remaining:
            raise AssertionError(
                f"fake_claude_status: called {len(self.calls)} time(s) but only "
                f"{len(self._triples)} triple(s) were provided; "
                f"unexpected argv={argv!r}"
            )
        return self._remaining.pop(0)

    def __enter__(self) -> "_FakeClaudeStatus":
        self._patcher = patch(_SEAM, side_effect=self._side_effect)
        self._patcher.start()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> bool:
        if self._patcher is not None:
            self._patcher.stop()
        if exc_type is None and self._remaining:
            raise AssertionError(
                f"fake_claude_status: {len(self._remaining)} un-consumed triple(s) "
                f"remaining at teardown out of {len(self._triples)} provided; "
                f"un-consumed={self._remaining!r}"
            )
        return False


@contextlib.contextmanager
def fake_claude_status(triples: Sequence[tuple[str, str, int]]):
    """Context manager that patches the claude-status subprocess seam.

    Yields a ``_FakeClaudeStatus`` instance whose ``.calls`` attribute
    records each invocation's full argv list.
    """
    ctx = _FakeClaudeStatus(triples)
    with ctx:
        yield ctx


# ---------------------------------------------------------------------------
# fake_worker_record — build a single Worker record dict (contract 1.0.0)
# ---------------------------------------------------------------------------

_DEFAULT_LABELS = {
    "claude_spawn_owned": "1",
    "claude_spawn_session_name": "worker-default",
    "claude_spawn_model": "claude-opus-4-5",
    "claude_spawn_repo": "/work/repo",
}

_VALID_STATUSES = frozenset(
    {"waiting", "working", "ask_user", "check_permission", "ended", "crashed"}
)


def fake_worker_record(
    instance_id: str,
    status: str,
    labels: dict | None = None,
    pending: dict | None = None,
) -> dict:
    """Return a Worker record dict matching the claude-status contract 1.0.0.

    ``status`` must be one of the six documented values.
    ``labels`` defaults to a minimal waggle-owned set when not supplied.
    ``pending`` defaults to ``None``.
    """
    if status not in _VALID_STATUSES:
        raise ValueError(
            f"fake_worker_record: status={status!r} not in {sorted(_VALID_STATUSES)}"
        )
    return {
        "instance_id": instance_id,
        "status": status,
        "host": "test-host",
        "cwd": "/work/repo",
        "transcript_path": None,
        "started_at": "2026-05-14T10:00:00.000000000Z",
        "last_seen_at": "2026-05-14T10:00:00.000000000Z",
        "ended_at": None,
        "labels": dict(_DEFAULT_LABELS) if labels is None else dict(labels),
        "pending": pending,
    }


# ---------------------------------------------------------------------------
# fake_workers_response — wrap records in the workers-verb envelope
# ---------------------------------------------------------------------------


def fake_workers_response(
    records: Sequence[dict], skipped: Sequence[Any] = ()
) -> dict:
    """Return ``{"workers": [...], "skipped": [...]}``."""
    return {"workers": list(records), "skipped": list(skipped)}


# ---------------------------------------------------------------------------
# fake_tmux_pane — minimal pane stub whose capture_pane() returns list[str]
# ---------------------------------------------------------------------------


class _FakeTmuxPane:
    """Minimal libtmux pane stub.

    ``capture_pane()`` returns the text split into lines, matching the
    list-of-strings shape libtmux's ``Pane.capture_pane()`` returns.
    """

    def __init__(self, text: str) -> None:
        self._lines = text.split("\n") if text else []

    def capture_pane(self, **kwargs: Any) -> list[str]:
        return list(self._lines)


def fake_tmux_pane(text: str) -> _FakeTmuxPane:
    """Return a fake libtmux pane whose ``capture_pane()`` returns ``text`` as lines."""
    return _FakeTmuxPane(text)
