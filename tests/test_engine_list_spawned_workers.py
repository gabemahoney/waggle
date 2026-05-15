"""Unit tests for waggle.spawn.list_spawned_workers_impl (SR-3.3).

Uses fake_claude_status from tests.helpers to patch waggle.claude_status._run.
No real subprocess is forked.  No conftest.py.
"""

from __future__ import annotations

import json
import sys

import pytest

import waggle.spawn as sp
from tests.helpers import fake_claude_status, fake_worker_record, fake_workers_response


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_response(*records):
    return json.dumps(fake_workers_response(list(records)))


# ---------------------------------------------------------------------------
# argv construction
# ---------------------------------------------------------------------------


class TestListSpawnedWorkersArgv:
    def test_passes_label_waggle_owned(self):
        payload = _make_response()
        with fake_claude_status([(payload, "", 0)]) as fcs:
            sp.list_spawned_workers_impl()
        argv = fcs.calls[0]
        assert "workers" in argv
        assert "--label" in argv
        idx = argv.index("--label")
        assert argv[idx + 1] == "waggle_owned=1"

    def test_exactly_one_seam_call(self):
        payload = _make_response()
        with fake_claude_status([(payload, "", 0)]) as fcs:
            sp.list_spawned_workers_impl()
        assert len(fcs.calls) == 1


# ---------------------------------------------------------------------------
# Happy path projection
# ---------------------------------------------------------------------------


class TestListSpawnedWorkersProjection:
    def test_projects_instance_id(self):
        r = fake_worker_record("inst-aaa", "working")
        payload = _make_response(r)
        with fake_claude_status([(payload, "", 0)]):
            result = sp.list_spawned_workers_impl()
        workers = result["workers"]
        assert workers[0]["instance_id"] == "inst-aaa"

    def test_projects_session_name_from_label(self):
        r = fake_worker_record("inst-bbb", "working")
        r["labels"]["waggle_session_name"] = "my-session"
        payload = _make_response(r)
        with fake_claude_status([(payload, "", 0)]):
            result = sp.list_spawned_workers_impl()
        assert result["workers"][0]["session_name"] == "my-session"

    def test_two_workers_projected(self):
        r1 = fake_worker_record("inst-1", "working")
        r2 = fake_worker_record("inst-2", "waiting")
        payload = _make_response(r1, r2)
        with fake_claude_status([(payload, "", 0)]):
            result = sp.list_spawned_workers_impl()
        assert len(result["workers"]) == 2

    def test_empty_workers_is_success(self):
        payload = _make_response()
        with fake_claude_status([(payload, "", 0)]):
            result = sp.list_spawned_workers_impl()
        assert "workers" in result
        assert result["workers"] == []

    def test_result_keys_are_instance_id_and_session_name_only(self):
        r = fake_worker_record("inst-ccc", "working")
        payload = _make_response(r)
        with fake_claude_status([(payload, "", 0)]):
            result = sp.list_spawned_workers_impl()
        entry = result["workers"][0]
        assert set(entry.keys()) == {"instance_id", "session_name"}


# ---------------------------------------------------------------------------
# Skipped rows
# ---------------------------------------------------------------------------


class TestListSpawnedWorkersSkipped:
    def test_skipped_rows_absent_from_workers(self):
        r = fake_worker_record("inst-good", "working")
        envelope = fake_workers_response([r], skipped=[{"instance_id": "inst-bad"}])
        payload = json.dumps(envelope)
        with fake_claude_status([(payload, "", 0)]):
            result = sp.list_spawned_workers_impl()
        ids = [w["instance_id"] for w in result["workers"]]
        assert "inst-good" in ids
        assert "inst-bad" not in ids

    def test_skipped_rows_logged_to_stderr(self, capsys):
        r = fake_worker_record("inst-good", "working")
        envelope = fake_workers_response([r], skipped=[{"instance_id": "inst-bad"}])
        payload = json.dumps(envelope)
        with fake_claude_status([(payload, "", 0)]):
            sp.list_spawned_workers_impl()
        err = capsys.readouterr().err
        assert "inst-bad" in err

    def test_no_skipped_rows_means_no_stderr(self, capsys):
        r = fake_worker_record("inst-good", "working")
        payload = _make_response(r)
        with fake_claude_status([(payload, "", 0)]):
            sp.list_spawned_workers_impl()
        err = capsys.readouterr().err
        assert err == ""


# ---------------------------------------------------------------------------
# Error propagation from claude_status
# ---------------------------------------------------------------------------


class TestListSpawnedWorkersErrors:
    def test_claude_status_error_propagates(self):
        from tests.sample_payloads import STDERR_ERR_STORE_UNAVAILABLE
        with fake_claude_status([("", STDERR_ERR_STORE_UNAVAILABLE, 1)]):
            result = sp.list_spawned_workers_impl()
        assert result.get("ok") is False
        assert result.get("err_name") == "ErrStoreUnavailable"
