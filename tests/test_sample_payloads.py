"""Structural-invariants tests for tests/sample_payloads.py.

Imports only from tests.sample_payloads; no claude_spawn.* production imports.
"""

import re

import tests.sample_payloads as sp

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VALID_STATUSES = {"waiting", "working", "ask_user", "check_permission", "ended", "crashed"}
_VALID_PENDING_KINDS = {"permission_request", "ask_user_question"}
_STDERR_RE = re.compile(
    r"^ERROR: (ErrInstanceNotFound|ErrNoPendingRequest|ErrSchemaMismatch"
    r"|ErrStoreUnavailable|ErrPayloadMalformed): .+\n$"
)

_WORKER_CONSTANTS = [
    sp.WORKER_WORKING,
    sp.WORKER_ASK_USER_SINGLE,
    sp.WORKER_ASK_USER_MULTI,
    sp.WORKER_ENDED,
    sp.WORKER_MALFORMED_LABELS,
]

_PENDING_CONSTANTS = [
    sp.PENDING_PERMISSION_REQUEST,
    sp.PENDING_ASK_USER_SINGLE,
    sp.PENDING_ASK_USER_MULTI,
]

_CAPABILITIES_CONSTANTS = [
    (sp.CAPABILITIES_V1, "1"),
    (sp.CAPABILITIES_V2, "2"),
]

_STDERR_CONSTANTS = [
    sp.STDERR_ERR_INSTANCE_NOT_FOUND,
    sp.STDERR_ERR_NO_PENDING_REQUEST,
    sp.STDERR_ERR_SCHEMA_MISMATCH,
    sp.STDERR_ERR_STORE_UNAVAILABLE,
    sp.STDERR_ERR_PAYLOAD_MALFORMED,
]

# ---------------------------------------------------------------------------
# Worker JSON dicts
# ---------------------------------------------------------------------------


def test_worker_required_keys():
    for w in _WORKER_CONSTANTS:
        assert "instance_id" in w, f"missing instance_id in {w}"
        assert "status" in w, f"missing status in {w}"
        assert "labels" in w, f"missing labels in {w}"
        assert "pending" in w, f"missing pending in {w}"


def test_worker_status_valid():
    for w in _WORKER_CONSTANTS:
        assert w["status"] in _VALID_STATUSES, (
            f"status={w['status']!r} not in valid set for instance {w['instance_id']}"
        )


def test_worker_labels_is_dict():
    for w in _WORKER_CONSTANTS:
        assert isinstance(w["labels"], dict), (
            f"labels is not a dict for instance {w['instance_id']}"
        )


def test_worker_pending_none_or_dict_with_kind():
    for w in _WORKER_CONSTANTS:
        p = w["pending"]
        if p is not None:
            assert isinstance(p, dict), (
                f"pending is not None or dict for instance {w['instance_id']}"
            )
            assert "kind" in p, (
                f"pending dict missing 'kind' for instance {w['instance_id']}"
            )


# ---------------------------------------------------------------------------
# Pending-payload dicts
# ---------------------------------------------------------------------------


def test_pending_kind_field_valid():
    for p in _PENDING_CONSTANTS:
        assert "kind" in p, f"pending payload missing 'kind': {p}"
        assert p["kind"] in _VALID_PENDING_KINDS, (
            f"pending kind={p['kind']!r} not in valid set"
        )


def test_pending_ask_user_has_questions_list():
    for p in _PENDING_CONSTANTS:
        if p["kind"] == "ask_user_question":
            assert isinstance(p.get("tool_input", {}).get("questions"), list), (
                f"ask_user_question payload missing tool_input.questions list: {p}"
            )


def test_pending_ask_user_multi_has_two_questions():
    p = sp.PENDING_ASK_USER_MULTI
    questions = p["tool_input"]["questions"]
    assert len(questions) == 2, (
        f"PENDING_ASK_USER_MULTI should have 2 questions, got {len(questions)}"
    )


def test_pending_ask_user_single_has_one_question():
    p = sp.PENDING_ASK_USER_SINGLE
    questions = p["tool_input"]["questions"]
    assert len(questions) == 1, (
        f"PENDING_ASK_USER_SINGLE should have 1 question, got {len(questions)}"
    )


# ---------------------------------------------------------------------------
# Capabilities response dicts
# ---------------------------------------------------------------------------


def test_capabilities_contract_version_key():
    for cap, _ in _CAPABILITIES_CONSTANTS:
        assert "contract_version" in cap, f"capabilities dict missing contract_version: {cap}"
        assert isinstance(cap["contract_version"], str), (
            f"contract_version is not a string: {cap['contract_version']!r}"
        )


def test_capabilities_v1_major_is_1():
    major = sp.CAPABILITIES_V1["contract_version"].split(".")[0]
    assert major == "1", f"CAPABILITIES_V1 major should be '1', got {major!r}"


def test_capabilities_v2_major_is_2():
    major = sp.CAPABILITIES_V2["contract_version"].split(".")[0]
    assert major == "2", f"CAPABILITIES_V2 major should be '2', got {major!r}"


# ---------------------------------------------------------------------------
# Stderr envelope strings
# ---------------------------------------------------------------------------


def test_stderr_envelopes_start_with_error_prefix():
    for s in _STDERR_CONSTANTS:
        assert s.startswith("ERROR: "), f"stderr envelope does not start with 'ERROR: ': {s!r}"


def test_stderr_envelopes_end_with_newline():
    for s in _STDERR_CONSTANTS:
        assert s.endswith("\n"), f"stderr envelope does not end with newline: {s!r}"


def test_stderr_envelopes_match_grammar():
    for s in _STDERR_CONSTANTS:
        assert _STDERR_RE.match(s), (
            f"stderr envelope does not match expected grammar: {s!r}"
        )


def test_stderr_each_errname_present():
    joined = "\n".join(_STDERR_CONSTANTS)
    for name in [
        "ErrInstanceNotFound",
        "ErrNoPendingRequest",
        "ErrSchemaMismatch",
        "ErrStoreUnavailable",
        "ErrPayloadMalformed",
    ]:
        assert name in joined, f"no stderr envelope contains ErrName={name!r}"
