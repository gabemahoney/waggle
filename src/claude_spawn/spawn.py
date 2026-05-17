"""Stateless spawn_worker and list_spawned_workers logic (SR-3.2, SR-3.3).

This module is the implementation backing for the new stdio MCP tools.
All tmux invocations go through the ``_tmux`` seam (patch target:
``claude_spawn.spawn._tmux``) so tests never fork real tmux processes.

No module-level side effects.  Import is inert.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import uuid

from claude_spawn import claude_status

# ---------------------------------------------------------------------------
# Subprocess seam — patch target: claude_spawn.spawn._tmux
# ---------------------------------------------------------------------------

_TMUX_TIMEOUT = 10


def _tmux(argv: list[str]) -> tuple[str, str, int]:
    """Run ``tmux <argv>`` in a fresh subprocess.

    Returns ``(stdout, stderr, returncode)``.  Never retries.
    """
    result = subprocess.run(
        ["tmux", *argv],
        capture_output=True,
        text=True,
        timeout=_TMUX_TIMEOUT,
    )
    return result.stdout, result.stderr, result.returncode


# ---------------------------------------------------------------------------
# Folder-name sanitiser (SR-3.2)
# ---------------------------------------------------------------------------

_SANITIZE_RE = re.compile(r"[^A-Za-z0-9_-]")


def _sanitize_folder_name(path: str) -> str:
    """Return a tmux-safe name derived from the final segment of *path* (SR-3.2)."""
    segment = os.path.basename(os.path.normpath(path))
    if not segment or segment == ".":
        return "root"
    sanitized = _SANITIZE_RE.sub("-", segment)
    if not sanitized or all(c == "-" for c in sanitized):
        return "root"
    return sanitized


# ---------------------------------------------------------------------------
# spawn_worker
# ---------------------------------------------------------------------------

_REQUIRED_ENV_VARS = (
    "CLAUDE_STATUS_INSTANCE_ID",
    "CLAUDE_STATUS_RELAY_MODE",
    "CLAUDE_STATUS_AUQ_MODE",
    "CLAUDE_STATUS_LABEL_CLAUDE_SPAWN_OWNED",
    "CLAUDE_STATUS_LABEL_CLAUDE_SPAWN_SESSION_NAME",
    "CLAUDE_STATUS_LABEL_CLAUDE_SPAWN_MODEL",
    "CLAUDE_STATUS_LABEL_CLAUDE_SPAWN_CWD",
)


def spawn_worker_impl(
    model: str,
    repo: str,
    session_name: str | None = None,
) -> dict:
    """Create a tmux session and launch Claude inside it.

    Returns ``{"instance_id": str, "session_name": str}`` on success or
    an SR-7.1 operation-failed dict on failure.  Never raises.
    """
    instance_id = str(uuid.uuid4())
    if session_name is None:
        session_name = f"spawn-{instance_id[:8]}"
    model_lower = model.lower()

    # Build env-injection args for tmux new-session.
    env_args: list[str] = []
    for key, val in [
        ("CLAUDE_STATUS_INSTANCE_ID", instance_id),
        ("CLAUDE_STATUS_RELAY_MODE", "on"),
        ("CLAUDE_STATUS_AUQ_MODE", "record"),
        ("CLAUDE_STATUS_LABEL_CLAUDE_SPAWN_OWNED", "1"),
        ("CLAUDE_STATUS_LABEL_CLAUDE_SPAWN_SESSION_NAME", session_name),
        ("CLAUDE_STATUS_LABEL_CLAUDE_SPAWN_MODEL", model_lower),
        ("CLAUDE_STATUS_LABEL_CLAUDE_SPAWN_CWD", repo),
    ]:
        env_args += ["-e", f"{key}={val}"]

    _stdout, stderr, rc = _tmux(
        ["new-session", "-d", "-s", session_name, *env_args]
    )
    if rc != 0:
        return {
            "ok": False,
            "operation": "spawn_worker",
            "err_name": "ErrTmuxSessionCreate",
            "err_description": stderr.strip() or "tmux new-session failed",
        }

    # Send the claude launch command to window 0, pane 0.
    _stdout2, stderr2, rc2 = _tmux(
        ["send-keys", "-t", f"{session_name}:0.0", f"claude --model {model_lower}", "Enter"]
    )
    if rc2 != 0:
        return {
            "ok": False,
            "operation": "spawn_worker",
            "err_name": "ErrTmuxSendKeys",
            "err_description": stderr2.strip() or "tmux send-keys failed",
        }

    return {"instance_id": instance_id, "session_name": session_name}


# ---------------------------------------------------------------------------
# list_spawned_workers
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# send_input
# ---------------------------------------------------------------------------


def send_input_impl(session_name: str, text: str) -> dict:
    """Send *text* verbatim (no implicit Enter) to window 0, pane 0.

    Returns ``{"ok": True, "operation": "send_input"}`` on success or an
    SR-7.1 operation-failed dict on failure.  Never raises.
    """
    _stdout, stderr, rc = _tmux(
        ["send-keys", "-t", f"{session_name}:0.0", text]
    )
    if rc != 0:
        return {
            "ok": False,
            "operation": "send_input",
            "err_name": "ErrTmuxSendKeys",
            "err_description": stderr.strip() or "tmux send-keys failed",
        }
    return {"ok": True, "operation": "send_input"}


# ---------------------------------------------------------------------------
# get_output
# ---------------------------------------------------------------------------

_SCROLLBACK_MIN = 1
_SCROLLBACK_MAX = 1000
_SCROLLBACK_DEFAULT = 50


def get_output_impl(session_name: str, scrollback: int | None = None) -> dict:
    """Capture window 0, pane 0 of *session_name*.

    *scrollback* must be in ``[1, 1000]`` or omitted (defaults to 50).
    Out-of-range values return operation-failed; they are NOT silently clamped.

    Returns ``{"ok": True, "operation": "get_output", "content": str}`` on
    success or an SR-7.1 operation-failed dict on failure.  Never raises.
    """
    if scrollback is None:
        scrollback = _SCROLLBACK_DEFAULT
    if not (_SCROLLBACK_MIN <= scrollback <= _SCROLLBACK_MAX):
        return {
            "ok": False,
            "operation": "get_output",
            "err_name": "ErrScrollbackOutOfRange",
            "err_description": (
                f"scrollback={scrollback!r} is out of range "
                f"[{_SCROLLBACK_MIN}, {_SCROLLBACK_MAX}]"
            ),
        }

    stdout, stderr, rc = _tmux(
        ["capture-pane", "-p", "-t", f"{session_name}:0.0", "-S", f"-{scrollback}"]
    )
    if rc != 0:
        return {
            "ok": False,
            "operation": "get_output",
            "err_name": "ErrTmuxCaptureFailed",
            "err_description": stderr.strip() or "tmux capture-pane failed",
        }
    return {"ok": True, "operation": "get_output", "content": stdout}


# ---------------------------------------------------------------------------
# terminate_worker
# ---------------------------------------------------------------------------


def terminate_worker_impl(session_name: str) -> dict:
    """Kill the tmux session named *session_name*.

    Claude Status records the worker as ``ended`` independently via its
    lifecycle hooks.  Returns ``{"ok": True, "operation": "terminate_worker"}``
    on success or an SR-7.1 operation-failed dict on failure.  Never raises.
    """
    _stdout, stderr, rc = _tmux(["kill-session", "-t", session_name])
    if rc != 0:
        return {
            "ok": False,
            "operation": "terminate_worker",
            "err_name": "ErrTmuxKillFailed",
            "err_description": stderr.strip() or "tmux kill-session failed",
        }
    return {"ok": True, "operation": "terminate_worker"}


# ---------------------------------------------------------------------------
# answer_question
# ---------------------------------------------------------------------------

import re as _re

_WS_RE = _re.compile(r"\s+")


def _normalize_ws(text: str) -> str:
    """Collapse runs of whitespace to a single space and strip."""
    return _WS_RE.sub(" ", text).strip()


def answer_question_impl(question_id: int, answer: str) -> dict:
    """Answer the pending AskUserQuestion identified by *question_id*.

    Implementation order (SR-3.5):
    1. Fetch Claude Spawn-owned workers via Claude Status.
    2. Find row with pending.kind=="ask_user_question" and
       pending.request_id==question_id.
    3. Refuse if questions list has length > 1 (ErrMultiQuestionUnsupported).
    4. Extract question text and session_name.
    5. Capture pane; whitespace-normalize both question and pane content;
       refuse if question not visible (ErrQuestionNoLongerVisible).
    6. Send answer + Enter in one send-keys call; return success.

    Never raises.
    """
    # Step 1: fetch workers
    cs_result = claude_status.workers(label="claude_spawn_owned=1")
    if not cs_result["ok"]:
        return {
            "ok": False,
            "operation": "answer_question",
            "err_name": cs_result["err_name"],
            "err_description": cs_result["err_description"],
        }

    # Step 2: find matching row
    matched = None
    for rec in cs_result["workers"].get("workers", []):
        pending = rec.get("pending") or {}
        if (
            pending.get("kind") == "ask_user_question"
            and pending.get("request_id") == question_id
        ):
            matched = rec
            break

    if matched is None:
        return {
            "ok": False,
            "operation": "answer_question",
            "err_name": "ErrNoPendingAskUserQuestion",
            "err_description": (
                f"no worker has a pending ask_user_question with request_id={question_id!r}"
            ),
        }

    pending = matched["pending"]
    questions = pending.get("tool_input", {}).get("questions", [])

    # Step 3: single-question constraint
    if len(questions) != 1:
        return {
            "ok": False,
            "operation": "answer_question",
            "err_name": "ErrMultiQuestionUnsupported",
            "err_description": (
                f"pending AUQ has {len(questions)} questions; "
                "only single-question AUQs are supported in v1"
            ),
        }

    # Step 4: extract question text and session_name
    question_text = questions[0].get("question", "")
    session_name = (matched.get("labels") or {}).get("claude_spawn_session_name", "")

    # Step 5: capture pane and verify question is visible
    stdout, stderr, rc = _tmux(
        ["capture-pane", "-p", "-t", f"{session_name}:0.0", "-S", "-50"]
    )
    if rc != 0:
        return {
            "ok": False,
            "operation": "answer_question",
            "err_name": "ErrTmuxCaptureFailed",
            "err_description": stderr.strip() or "tmux capture-pane failed",
        }

    norm_question = _normalize_ws(question_text)
    norm_pane = _normalize_ws(stdout)
    if norm_question not in norm_pane:
        return {
            "ok": False,
            "operation": "answer_question",
            "err_name": "ErrQuestionNoLongerVisible",
            "err_description": (
                f"question text {question_text!r} not found in pane 0 of {session_name!r}; "
                "the worker may have moved on"
            ),
        }

    # Step 6: send answer + Enter
    _stdout2, stderr2, rc2 = _tmux(
        ["send-keys", "-t", f"{session_name}:0.0", answer, "Enter"]
    )
    if rc2 != 0:
        return {
            "ok": False,
            "operation": "answer_question",
            "err_name": "ErrTmuxSendKeys",
            "err_description": stderr2.strip() or "tmux send-keys failed",
        }

    return {"ok": True, "operation": "answer_question"}


# ---------------------------------------------------------------------------
# list_spawned_workers
# ---------------------------------------------------------------------------


def list_spawned_workers_impl() -> dict:
    """Query Claude Status for Claude Spawn-owned workers and project to ID pairs.

    Returns ``{"workers": [{instance_id, session_name}, ...]}`` on success or
    an SR-7.1 operation-failed dict on failure.  Skipped rows are logged to
    stderr but excluded from the returned list.  Never raises.
    """
    result = claude_status.workers(label="claude_spawn_owned=1")
    if not result["ok"]:
        return result  # SR-7.1 failure from the client propagates unchanged

    envelope = result["workers"]
    projected = []
    for rec in envelope.get("workers", []):
        labels = rec.get("labels") or {}
        projected.append({
            "instance_id": rec["instance_id"],
            "session_name": labels.get("claude_spawn_session_name", ""),
        })

    for skipped in envelope.get("skipped", []):
        iid = skipped.get("instance_id", "<unknown>") if isinstance(skipped, dict) else repr(skipped)
        print(
            f"list_spawned_workers: skipped row instance_id={iid!r}",
            file=sys.stderr,
        )

    return {"workers": projected}
