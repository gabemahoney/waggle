"""Unit tests for waggle.claude_status (SR-2.3, SR-7.1).

Tests are split into two logical groups:
- Verb-shape and capability-pin (success paths, argv construction, version pin)
- Typed-error, malformed-stderr, timeout, and missing-binary (failure paths)

All JSON payloads are sourced from tests.sample_payloads — no inline literals.
No conftest.py.  No imports from waggle.* other than waggle.claude_status.
"""

from __future__ import annotations

import json
import subprocess
from unittest.mock import patch

import pytest

import waggle.claude_status as cs
from tests.helpers import fake_claude_status, fake_worker_record, fake_workers_response
from tests.sample_payloads import (
    CAPABILITIES_V1,
    CAPABILITIES_V2,
    STDERR_ERR_INSTANCE_NOT_FOUND,
    STDERR_ERR_NO_PENDING_REQUEST,
    STDERR_ERR_PAYLOAD_MALFORMED,
    STDERR_ERR_SCHEMA_MISMATCH,
    STDERR_ERR_STORE_UNAVAILABLE,
    WORKER_WORKING,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_EMPTY_WORKERS = fake_workers_response([])
_TWO_WORKERS = fake_workers_response(
    [fake_worker_record("a", "working"), fake_worker_record("b", "waiting")]
)


# ---------------------------------------------------------------------------
# workers() — verb-shape tests
# ---------------------------------------------------------------------------


class TestWorkersVerb:
    def test_no_label_argv(self):
        payload = json.dumps(_EMPTY_WORKERS)
        with fake_claude_status([(payload, "", 0)]) as fcs:
            result = cs.workers()
        assert fcs.calls[0][0] == "workers"
        assert "--label" not in fcs.calls[0]

    def test_with_label_argv(self):
        payload = json.dumps(_EMPTY_WORKERS)
        with fake_claude_status([(payload, "", 0)]) as fcs:
            result = cs.workers(label="waggle_owned=1")
        argv = fcs.calls[0]
        assert argv[0] == "workers"
        assert "--label" in argv
        idx = argv.index("--label")
        assert argv[idx + 1] == "waggle_owned=1"

    def test_label_as_two_separate_entries(self):
        payload = json.dumps(_EMPTY_WORKERS)
        with fake_claude_status([(payload, "", 0)]) as fcs:
            cs.workers(label="waggle_owned=1")
        argv = fcs.calls[0]
        # --label and the value must be adjacent separate entries
        idx = argv.index("--label")
        assert argv[idx + 1] == "waggle_owned=1"
        assert "--label=waggle_owned=1" not in argv

    def test_returns_operation_success(self):
        payload = json.dumps(_EMPTY_WORKERS)
        with fake_claude_status([(payload, "", 0)]):
            result = cs.workers()
        assert result["ok"] is True
        assert result["operation"] == "workers"

    def test_empty_workers_list_is_success(self):
        payload = json.dumps(fake_workers_response([]))
        with fake_claude_status([(payload, "", 0)]):
            result = cs.workers()
        assert result["ok"] is True
        assert result["workers"]["workers"] == []

    def test_two_workers_parsed(self):
        payload = json.dumps(_TWO_WORKERS)
        with fake_claude_status([(payload, "", 0)]):
            result = cs.workers()
        assert result["ok"] is True
        assert len(result["workers"]["workers"]) == 2

    def test_exactly_one_seam_invocation(self):
        payload = json.dumps(_EMPTY_WORKERS)
        with fake_claude_status([(payload, "", 0)]) as fcs:
            cs.workers()
        assert len(fcs.calls) == 1


# ---------------------------------------------------------------------------
# worker() — verb-shape tests
# ---------------------------------------------------------------------------


class TestWorkerVerb:
    def test_argv_construction(self):
        payload = json.dumps(WORKER_WORKING)
        with fake_claude_status([(payload, "", 0)]) as fcs:
            cs.worker("inst-xyz")
        assert fcs.calls[0] == ["worker", "inst-xyz"]

    def test_returns_operation_success(self):
        payload = json.dumps(WORKER_WORKING)
        with fake_claude_status([(payload, "", 0)]):
            result = cs.worker("inst-working-001")
        assert result["ok"] is True
        assert result["operation"] == "worker"

    def test_parsed_payload_matches_canonical(self):
        payload = json.dumps(WORKER_WORKING)
        with fake_claude_status([(payload, "", 0)]):
            result = cs.worker("inst-working-001")
        assert result["worker"]["instance_id"] == WORKER_WORKING["instance_id"]
        assert result["worker"]["status"] == WORKER_WORKING["status"]

    def test_exactly_one_seam_invocation(self):
        payload = json.dumps(WORKER_WORKING)
        with fake_claude_status([(payload, "", 0)]) as fcs:
            cs.worker("inst-working-001")
        assert len(fcs.calls) == 1


# ---------------------------------------------------------------------------
# capabilities() — success-path and contract-version pin tests
# ---------------------------------------------------------------------------


class TestCapabilitiesVerb:
    def test_argv_is_capabilities(self):
        payload = json.dumps(CAPABILITIES_V1)
        with fake_claude_status([(payload, "", 0)]) as fcs:
            cs.capabilities()
        assert fcs.calls[0] == ["capabilities"]

    def test_v1_is_success(self):
        payload = json.dumps(CAPABILITIES_V1)
        with fake_claude_status([(payload, "", 0)]):
            result = cs.capabilities()
        assert result["ok"] is True
        assert result["operation"] == "capabilities"

    def test_v2_is_refused(self):
        payload = json.dumps(CAPABILITIES_V2)
        with fake_claude_status([(payload, "", 0)]):
            result = cs.capabilities()
        assert result["ok"] is False
        assert result["err_name"] == "ErrContractVersionMismatch"

    @pytest.mark.parametrize("version", ["1.0.0", "1.7.3", "1.0"])
    def test_accepted_versions(self, version):
        cap = dict(CAPABILITIES_V1, contract_version=version)
        payload = json.dumps(cap)
        with fake_claude_status([(payload, "", 0)]):
            result = cs.capabilities()
        assert result["ok"] is True

    @pytest.mark.parametrize(
        "version",
        [
            "2.0.0",   # major 2
            "0.9.0",   # major 0
            "1",       # no dot — malformed
            "abc.0",   # non-numeric major
        ],
    )
    def test_refused_versions(self, version):
        cap = dict(CAPABILITIES_V1, contract_version=version)
        payload = json.dumps(cap)
        with fake_claude_status([(payload, "", 0)]):
            result = cs.capabilities()
        assert result["ok"] is False
        assert result["err_name"] == "ErrContractVersionMismatch"

    def test_missing_contract_version_key(self):
        cap = {k: v for k, v in CAPABILITIES_V1.items() if k != "contract_version"}
        payload = json.dumps(cap)
        with fake_claude_status([(payload, "", 0)]):
            result = cs.capabilities()
        assert result["ok"] is False
        assert result["err_name"] == "ErrContractVersionMismatch"

    def test_non_string_contract_version(self):
        cap = dict(CAPABILITIES_V1, contract_version=1)
        payload = json.dumps(cap)
        with fake_claude_status([(payload, "", 0)]):
            result = cs.capabilities()
        assert result["ok"] is False
        assert result["err_name"] == "ErrContractVersionMismatch"

    def test_exactly_one_seam_invocation(self):
        payload = json.dumps(CAPABILITIES_V1)
        with fake_claude_status([(payload, "", 0)]) as fcs:
            cs.capabilities()
        assert len(fcs.calls) == 1


# ---------------------------------------------------------------------------
# Typed-error round-trip tests (SR-2.3 — ErrName preserved verbatim)
# ---------------------------------------------------------------------------


_TYPED_ERRORS = [
    ("ErrInstanceNotFound", STDERR_ERR_INSTANCE_NOT_FOUND),
    ("ErrNoPendingRequest", STDERR_ERR_NO_PENDING_REQUEST),
    ("ErrSchemaMismatch", STDERR_ERR_SCHEMA_MISMATCH),
    ("ErrStoreUnavailable", STDERR_ERR_STORE_UNAVAILABLE),
    ("ErrPayloadMalformed", STDERR_ERR_PAYLOAD_MALFORMED),
]


@pytest.mark.parametrize("err_name,stderr_str", _TYPED_ERRORS)
def test_typed_error_roundtrip(err_name, stderr_str):
    """Each ErrName propagates verbatim; exactly one subprocess invocation."""
    with fake_claude_status([("", stderr_str, 1)]) as fcs:
        result = cs.workers()
    assert result["ok"] is False
    assert result["err_name"] == err_name
    assert len(fcs.calls) == 1


# ---------------------------------------------------------------------------
# Malformed stderr — fallback sentinel
# ---------------------------------------------------------------------------


def test_malformed_stderr_returns_sentinel():
    with fake_claude_status([("", "some unexpected text\n", 1)]):
        result = cs.workers()
    assert result["ok"] is False
    assert result["err_name"] == "ErrMalformedErrorEnvelope"


def test_malformed_stderr_no_colon_returns_sentinel():
    """Malformed stderr without colon structure returns the sentinel err_name."""
    with fake_claude_status([("", "no colon here", 1)]):
        result = cs.workers()
    assert result["ok"] is False
    assert result["err_name"] == "ErrMalformedErrorEnvelope"


# ---------------------------------------------------------------------------
# Non-JSON stdout on exit 0
# ---------------------------------------------------------------------------


def test_non_json_stdout_exit_0_is_payload_malformed():
    with fake_claude_status([("not json\n", "", 0)]):
        result = cs.workers()
    assert result["ok"] is False
    assert result["err_name"] == "ErrPayloadMalformed"


# ---------------------------------------------------------------------------
# Missing binary (FileNotFoundError)
# ---------------------------------------------------------------------------


def test_missing_binary_returns_not_found():
    with patch("waggle.claude_status._run", side_effect=FileNotFoundError):
        result = cs.workers()
    assert result["ok"] is False
    assert result["err_name"] == "ErrClaudeStatusNotFound"


def test_missing_binary_one_invocation():
    call_count = 0

    def raise_fnf(argv):
        nonlocal call_count
        call_count += 1
        raise FileNotFoundError

    with patch("waggle.claude_status._run", side_effect=raise_fnf):
        cs.workers()
    assert call_count == 1


# ---------------------------------------------------------------------------
# Timeout (subprocess.TimeoutExpired)
# ---------------------------------------------------------------------------


def test_timeout_returns_timeout_err():
    exc = subprocess.TimeoutExpired(cmd="claude-status", timeout=10)
    with patch("waggle.claude_status._run", side_effect=exc):
        result = cs.workers()
    assert result["ok"] is False
    assert result["err_name"] == "ErrClaudeStatusTimeout"


def test_timeout_one_invocation():
    call_count = 0
    exc = subprocess.TimeoutExpired(cmd="claude-status", timeout=10)

    def raise_timeout(argv):
        nonlocal call_count
        call_count += 1
        raise exc

    with patch("waggle.claude_status._run", side_effect=raise_timeout):
        cs.workers()
    assert call_count == 1


# ---------------------------------------------------------------------------
# Import inertia — no subprocess at import time
# ---------------------------------------------------------------------------


def test_import_is_inert():
    """Confirm no subprocess is forked at module import time.

    Uses importlib.reload() which re-executes the module body *in place*
    (preserving the existing module object and all external references to it).
    If any top-level code in claude_status.py called subprocess.run, the
    patched version would raise immediately and the test would fail.
    """
    import importlib
    import waggle.claude_status as _mod

    with patch("subprocess.run", side_effect=AssertionError("subprocess.run called at import")) as mock_run:
        # reload() re-runs all module-level statements in the existing module
        # object — no new object is created, no external references are broken.
        importlib.reload(_mod)
    assert mock_run.call_count == 0, (
        f"subprocess.run was called {mock_run.call_count} time(s) during module reload"
    )


# ---------------------------------------------------------------------------
# decide is not exported
# ---------------------------------------------------------------------------


def test_decide_not_exported():
    assert not hasattr(cs, "decide"), "waggle.claude_status must not export 'decide'"
