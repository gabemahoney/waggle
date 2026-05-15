"""Claude Status consumer-CLI client (SR-2.2, SR-2.3, SR-7.1).

This module is the *only* path through which Waggle interacts with Claude
Status.  Every invocation spawns a fresh ``claude-status`` subprocess (no
connection pooling, no retry).

## Result shape (SR-7.1)

Every public function returns a plain ``dict``.  The discriminator is the
``"ok"`` key (``bool``).

Success::

    {
        "ok": True,
        "operation": "<verb>",          # "workers" | "worker" | "capabilities"
        "<verb>": <parsed-JSON-payload> # key matches operation
    }

Failure::

    {
        "ok": False,
        "operation": "<verb>",
        "err_name": "<ErrName>",
        "err_description": "<human-readable detail>"
    }

## err_name catalogue

**Claude-Status-originated** (parsed verbatim from stderr envelope
``ERROR: <ErrName>: <description>\\n``):

- ``ErrInstanceNotFound``   — no instance matches the given instance_id
- ``ErrNoPendingRequest``   — instance has no pending request of the expected kind
- ``ErrSchemaMismatch``     — DB schema version does not match binary
- ``ErrStoreUnavailable``   — cannot open / read the Claude Status database
- ``ErrPayloadMalformed``   — stored payload failed validation

**Waggle-originated** (produced internally; never emitted by claude-status):

- ``ErrMalformedErrorEnvelope``  — stderr did not match the documented grammar
- ``ErrContractVersionMismatch`` — ``capabilities`` reported a contract major != 1
- ``ErrClaudeStatusNotFound``    — ``claude-status`` binary not found on PATH
- ``ErrClaudeStatusTimeout``     — subprocess exceeded the bounded timeout

## Subprocess seam

The private function ``_run(argv)`` is the single subprocess invocation point.
All tests patch ``waggle.claude_status._run`` to avoid forking real processes.
The seam timeout is ``_TIMEOUT_SECONDS`` (10 s) and is documented here so
downstream callers know the upper bound.

## Import inertia

``import waggle.claude_status`` performs no subprocess fork, no PATH lookup,
and no file I/O.  The capability-pin enforcement (SR-2.2 startup check) is
the responsibility of the MCP server layer (sibling Epic t1.fg8.vv); this
module only provides the ``capabilities()`` verb function.
"""

from __future__ import annotations

import json
import re
import subprocess

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_TIMEOUT_SECONDS = 10
# No re.DOTALL: dot must not match newline so (.+) stops before the trailing \n,
# keeping err_description free of a trailing newline.
_STDERR_RE = re.compile(r"^ERROR: ([A-Z][A-Za-z0-9]*): (.+)\n?$")

# ---------------------------------------------------------------------------
# Subprocess seam — patch target: waggle.claude_status._run
# ---------------------------------------------------------------------------


def _run(argv: list[str]) -> tuple[str, str, int]:
    """Invoke ``claude-status <argv>`` in a fresh subprocess.

    Returns ``(stdout, stderr, exit_code)``.  Propagates
    ``FileNotFoundError`` and ``subprocess.TimeoutExpired`` to the caller
    (the shared helper translates them into structured results).

    Never retries.  One call = one subprocess.
    """
    result = subprocess.run(
        ["claude-status", *argv],
        capture_output=True,
        text=True,
        timeout=_TIMEOUT_SECONDS,
    )
    return result.stdout, result.stderr, result.returncode


# ---------------------------------------------------------------------------
# Stderr envelope parser
# ---------------------------------------------------------------------------


def _parse_stderr(stderr: str) -> tuple[str, str]:
    """Parse ``ERROR: <ErrName>: <description>\\n`` from *stderr*.

    Returns ``(err_name, description)``.  If the line does not match the
    documented grammar, returns the sentinel
    ``("ErrMalformedErrorEnvelope", stderr)`` so callers always receive a
    structured pair.
    """
    m = _STDERR_RE.match(stderr)
    if m:
        return m.group(1), m.group(2)
    return "ErrMalformedErrorEnvelope", stderr


# ---------------------------------------------------------------------------
# Shared internal call helper
# ---------------------------------------------------------------------------


def _call(operation: str, argv: list[str]) -> dict:
    """Invoke the seam, parse the result, and return a SR-7.1 result dict.

    Translates every failure mode into a structured operation-failed result;
    never raises.
    """
    try:
        stdout, stderr, exit_code = _run(argv)
    except FileNotFoundError:
        return {
            "ok": False,
            "operation": operation,
            "err_name": "ErrClaudeStatusNotFound",
            "err_description": (
                "claude-status binary not found on PATH; "
                "ensure claude-status is installed and on PATH"
            ),
        }
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "operation": operation,
            "err_name": "ErrClaudeStatusTimeout",
            "err_description": (
                f"claude-status did not complete within {_TIMEOUT_SECONDS}s"
            ),
        }

    if exit_code != 0:
        err_name, err_description = _parse_stderr(stderr)
        return {
            "ok": False,
            "operation": operation,
            "err_name": err_name,
            "err_description": err_description,
        }

    # exit 0 — parse JSON
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError:
        return {
            "ok": False,
            "operation": operation,
            "err_name": "ErrPayloadMalformed",
            "err_description": (
                f"claude-status exited 0 but stdout is not valid JSON: {stdout!r}"
            ),
        }

    return {
        "ok": True,
        "operation": operation,
        operation: payload,
    }


# ---------------------------------------------------------------------------
# Public verb functions
# ---------------------------------------------------------------------------


def workers(label: str | None = None) -> dict:
    """Call ``claude-status workers [--label <label>]``.

    Returns an operation-success result whose ``"workers"`` key holds the
    parsed ``{"workers": [...], "skipped": [...]}`` envelope from Claude
    Status.  An empty ``workers`` list is operation-success, not failure.

    ``label`` is passed through verbatim as two separate argv entries
    (``--label``, ``<label>``); this module does not validate label syntax.
    """
    argv: list[str] = ["workers"]
    if label is not None:
        argv += ["--label", label]
    return _call("workers", argv)


def worker(instance_id: str) -> dict:
    """Call ``claude-status worker <instance_id>``.

    Returns an operation-success result whose ``"worker"`` key holds the
    parsed Worker JSON dict.
    """
    return _call("worker", ["worker", instance_id])


def capabilities() -> dict:
    """Call ``claude-status capabilities`` and apply the contract-version pin.

    On operation-success from the subprocess: inspects ``contract_version``,
    expects the major component to be exactly ``1``.  Returns
    operation-failed with ``err_name=ErrContractVersionMismatch`` for any
    other major (including ``0``, ``2``, …) or any parse failure (missing
    key, non-string value, no dot separator, non-numeric major).

    This function does NOT enforce the pin at import time (SR-2.2 startup
    enforcement belongs to the MCP server layer in t1.fg8.vv).

    **Version string parsing policy:** ``contract_version`` must be a
    dot-separated string whose first component is the decimal integer ``1``.
    Strings with no dot separator (e.g. ``"1"``) are treated as
    **malformed** (major indeterminate) and return
    ``ErrContractVersionMismatch``.  Two-component strings (e.g. ``"1.0"``)
    follow the same rule: the first component must be ``"1"``, and such a
    string is accepted.
    """
    result = _call("capabilities", ["capabilities"])
    if not result["ok"]:
        return result

    payload = result["capabilities"]

    # Parse contract_version major
    cv = payload.get("contract_version")
    if not isinstance(cv, str):
        return {
            "ok": False,
            "operation": "capabilities",
            "err_name": "ErrContractVersionMismatch",
            "err_description": (
                f"contract_version missing or not a string: {cv!r}"
            ),
        }

    parts = cv.split(".")
    if len(parts) < 2:
        # No dot separator — cannot reliably determine major
        return {
            "ok": False,
            "operation": "capabilities",
            "err_name": "ErrContractVersionMismatch",
            "err_description": (
                f"contract_version has no dot separator: {cv!r}"
            ),
        }

    try:
        major = int(parts[0])
    except ValueError:
        return {
            "ok": False,
            "operation": "capabilities",
            "err_name": "ErrContractVersionMismatch",
            "err_description": (
                f"contract_version major is not an integer: {parts[0]!r}"
            ),
        }

    if major != 1:
        return {
            "ok": False,
            "operation": "capabilities",
            "err_name": "ErrContractVersionMismatch",
            "err_description": (
                f"contract_version major is {major}, expected 1; "
                f"full version: {cv!r}"
            ),
        }

    return result
