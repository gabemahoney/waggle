"""Stateless spawn_worker and list_spawned_workers logic (SR-3.2, SR-3.3).

This module is the implementation backing for the new stdio MCP tools.
All tmux invocations go through the ``_tmux`` seam (patch target:
``claude_spawn.spawn._tmux``) so tests never fork real tmux processes.

No module-level side effects.  Import is inert.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import time
import uuid

from claude_spawn import claude_status
from claude_spawn import templates as _templates_module

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

# SR-4.2 unconditional built-in env vars (excludes _MODEL, which is conditional)
_REQUIRED_ENV_VARS = (
    "CLAUDE_STATUS_INSTANCE_ID",
    "CLAUDE_STATUS_RELAY_MODE",
    "CLAUDE_STATUS_AUQ_MODE",
    "CLAUDE_STATUS_LABEL_CLAUDE_SPAWN_OWNED",
    "CLAUDE_STATUS_LABEL_CLAUDE_SPAWN_SESSION_NAME",
    "CLAUDE_STATUS_LABEL_CLAUDE_SPAWN_CWD",
)

_THINKING_VALID = {"low", "medium", "high", "xhigh"}

# SR-5.2: readiness polling timeout (seconds); not exposed as a caller param (SR-13)
_SPAWN_READINESS_TIMEOUT = 15

# Keys claude-spawn always emits itself (extra_env must not collide with these)
_RESERVED_ENV_KEYS = set(_REQUIRED_ENV_VARS) | {"CLAUDE_STATUS_LABEL_CLAUDE_SPAWN_MODEL"}

# Label keys claude-spawn always emits (claude_status_labels must not collide with these)
_RESERVED_LABEL_KEYS = frozenset(
    {"CLAUDE_SPAWN_OWNED", "CLAUDE_SPAWN_SESSION_NAME", "CLAUDE_SPAWN_CWD", "CLAUDE_SPAWN_MODEL"}
)


def _merge_maps(per_call: dict | None, tmpl: dict | None) -> dict:
    """SR-2.2 shallow map merge: union, per-call entries win on colliding top-level keys.

    ``None`` per-call is treated as "not supplied" — the template value (or ``{}``) is
    returned unchanged.  An explicit empty dict (``per_call={}``) enters the merge path:
    template-only keys survive because there are no per-call entries to override them.
    """
    base = dict(tmpl) if tmpl else {}
    if per_call is None:
        return base
    return {**base, **per_call}  # per-call wins on collisions


def _resolve_options(
    tmpl_opts: dict,
    *,
    cwd: str | None,
    model: str | None,
    thinking: str | None,
    tmux_session_name: str | None,
    instance_id: str | None,
    claude_home: str | None,
    claude_settings: str | None,
    extra_env: dict | None,
    claude_status_labels: dict | None,
    claude_args: list | None,
    permissions: dict | None,
) -> dict:
    """Apply SR-2.1 resolution chain (per-call → template → None).

    SR-2.3: scalar and list fields use wholesale replacement — per-call non-``None``
    value replaces the template value entirely.

    SR-2.2: map fields (``extra_env``, ``claude_status_labels``, ``permissions``) use
    shallow union merge — per-call entries win on colliding top-level keys while
    independent template-only keys are preserved.  Map results are always ``dict``
    (never ``None``).

    Scalar results may still be ``None`` when neither source supplied a value; callers
    apply SR-1.3 defaults afterward.  The list ``claude_args`` is ``None`` when absent
    from both sources; callers default it to ``[]``.
    """
    def _scalar(name: str, per_call_val):
        return per_call_val if per_call_val is not None else tmpl_opts.get(name)

    resolved: dict = {
        "cwd": _scalar("cwd", cwd),
        "model": _scalar("model", model),
        "thinking": _scalar("thinking", thinking),
        "tmux_session_name": _scalar("tmux_session_name", tmux_session_name),
        "instance_id": _scalar("instance_id", instance_id),
        "claude_home": _scalar("claude_home", claude_home),
        "claude_settings": _scalar("claude_settings", claude_settings),
    }

    # List (SR-2.3): per-call replaces wholesale; None → apply [] default later
    if claude_args is not None:
        resolved["claude_args"] = claude_args
    elif "claude_args" in tmpl_opts:
        resolved["claude_args"] = list(tmpl_opts["claude_args"])
    else:
        resolved["claude_args"] = None

    # Maps (SR-2.2): shallow merge; always produces a dict
    resolved["extra_env"] = _merge_maps(extra_env, tmpl_opts.get("extra_env"))
    resolved["claude_status_labels"] = _merge_maps(
        claude_status_labels, tmpl_opts.get("claude_status_labels")
    )
    resolved["permissions"] = _merge_maps(permissions, tmpl_opts.get("permissions"))

    return resolved


def _err_spawn(err_name: str, err_description: str) -> dict:
    return {
        "ok": False,
        "operation": "spawn_worker",
        "err_name": err_name,
        "err_description": err_description,
    }


def _resolve_settings_path(
    permissions: dict,
    claude_settings: str | None,
) -> str | None:
    """SR-4.5: synthesise the effective --settings path, or return None."""
    has_perms = bool(permissions)
    has_settings = bool(claude_settings)

    if not has_perms and not has_settings:
        return None

    if has_perms and not has_settings:
        data = {"permissions": permissions}
        with tempfile.NamedTemporaryFile(
            prefix="claude-spawn-settings-", suffix=".json", delete=False, mode="w"
        ) as f:
            json.dump(data, f)
            return f.name

    if has_settings and not has_perms:
        return claude_settings

    # composite: caller's file + per-call permissions (first-class wins on allow/deny/ask)
    try:
        with open(claude_settings) as f:  # type: ignore[arg-type]
            base = json.load(f)
    except json.JSONDecodeError as exc:
        return {
            "ok": False,
            "operation": "spawn_worker",
            "err_name": "ErrClaudeSettingsMalformed",
            "err_description": f"claude_settings {claude_settings!r}: JSON parse error: {exc}",
        }

    raw_perms = base.get("permissions")
    if raw_perms is not None and not isinstance(raw_perms, dict):
        return {
            "ok": False,
            "operation": "spawn_worker",
            "err_name": "ErrClaudeSettingsMalformed",
            "err_description": (
                f"claude_settings {claude_settings!r}: 'permissions' must be an object,"
                f" got {type(raw_perms).__name__}"
            ),
        }
    base_perms: dict = raw_perms if raw_perms is not None else {}
    for key in ("allow", "deny", "ask"):
        if key in permissions:
            base_perms[key] = permissions[key]
    base["permissions"] = base_perms

    with tempfile.NamedTemporaryFile(
        prefix="claude-spawn-settings-", suffix=".json", delete=False, mode="w"
    ) as f:
        json.dump(base, f)
        return f.name


def spawn_worker_impl(
    cwd: str | None = None,
    template: str | None = None,
    model: str | None = None,
    thinking: str | None = None,
    tmux_session_name: str | None = None,
    instance_id: str | None = None,
    claude_home: str | None = None,
    claude_settings: str | None = None,
    extra_env: dict[str, str] | None = None,
    claude_status_labels: dict[str, str] | None = None,
    claude_args: list[str] | None = None,
    permissions: dict | None = None,
) -> dict:
    """Create a tmux session and launch Claude inside it.

    Returns ``{"instance_id": str, "tmux_session_name": str}`` on success or
    an SR-7.1 operation-failed dict on failure.  Never raises.

    *template* names a TOML template to load from the templates directory.  When
    supplied, its option-map is merged with the per-call arguments following the
    SR-2.1 resolution chain:

      1. Per-call value (any non-``None`` argument) — takes precedence.
      2. Template value — used when the per-call argument is ``None``.
      3. SR-1.3 default — used when neither source provides a value.

    Map fields (``extra_env``, ``claude_status_labels``, ``permissions``):
    SR-2.2 shallow merge — per-call entries win on colliding top-level keys;
    independent keys from either source are preserved.  A non-``None`` but empty
    per-call dict enters the merge path: template-only keys survive because there
    are no per-call entries to override them.

    Scalar and list fields (SR-2.3): per-call value replaces the template value
    wholesale when per-call is not ``None``.
    """
    # Capture before resolution: collision check fires only for per-call-supplied
    # instance_id, not one inherited from a template.
    caller_supplied_instance_id = instance_id is not None

    # --- SR-6.6 fast path: skip loader entirely when template is not supplied ---
    if template is not None:
        load_result = _templates_module.load_template(template)
        if not load_result["ok"]:
            return load_result  # propagate ErrTemplateNotFound / ErrTemplateMalformed verbatim
        tmpl_opts: dict = load_result["load_template"]
    else:
        tmpl_opts = {}

    # --- SR-2.1 / SR-2.2 / SR-2.3 option resolution ---
    resolved = _resolve_options(
        tmpl_opts,
        cwd=cwd,
        model=model,
        thinking=thinking,
        tmux_session_name=tmux_session_name,
        instance_id=instance_id,
        claude_home=claude_home,
        claude_settings=claude_settings,
        extra_env=extra_env,
        claude_status_labels=claude_status_labels,
        claude_args=claude_args,
        permissions=permissions,
    )
    cwd = resolved["cwd"]
    model = resolved["model"]
    thinking = resolved["thinking"]
    tmux_session_name = resolved["tmux_session_name"]
    instance_id = resolved["instance_id"]
    claude_home = resolved["claude_home"]
    claude_settings = resolved["claude_settings"]
    extra_env = resolved["extra_env"]                          # dict, never None
    claude_status_labels = resolved["claude_status_labels"]    # dict, never None
    permissions = resolved["permissions"]                      # dict, never None
    claude_args = resolved["claude_args"] if resolved["claude_args"] is not None else []

    # --- SR-9.1 validation (all checks before any tmux call) ---

    # ErrCwdMissing
    if not cwd:
        return _err_spawn("ErrCwdMissing", "cwd is required but was not supplied")

    # ErrCwdNotAPath — reject URLs and relative paths
    if "://" in cwd:
        return _err_spawn("ErrCwdNotAPath", f"cwd {cwd!r} is a URL, not a filesystem path")

    expanded_cwd = os.path.expanduser(cwd)
    if not os.path.isabs(expanded_cwd):
        return _err_spawn(
            "ErrCwdNotAPath",
            f"cwd {cwd!r} is a relative path; supply an absolute path or ~/...",
        )

    # ErrCwdNotFound
    if not os.path.exists(expanded_cwd):
        return _err_spawn("ErrCwdNotFound", f"cwd {expanded_cwd!r} does not exist")

    # ErrThinkingInvalid
    if thinking is not None and thinking not in _THINKING_VALID:
        return _err_spawn(
            "ErrThinkingInvalid",
            f"thinking {thinking!r} is not valid; must be one of: low, medium, high, xhigh",
        )

    # ErrClaudeSettingsNotFound
    if claude_settings is not None and not os.path.exists(claude_settings):
        return _err_spawn(
            "ErrClaudeSettingsNotFound",
            f"claude_settings path {claude_settings!r} does not exist",
        )

    # ErrClaudeArgsSettingsConflict
    if claude_args:
        has_settings_flag = any(
            a == "--settings" or a.startswith("--settings=")
            for a in claude_args
        )
        if has_settings_flag and (claude_settings or bool(permissions)):
            return _err_spawn(
                "ErrClaudeArgsSettingsConflict",
                "--settings appears in claude_args but claude_settings (or permissions) is also "
                "supplied; pass settings via one mechanism only",
            )

    # ErrReservedEnvKey
    reserved_check = set(_RESERVED_ENV_KEYS)
    if claude_home:
        reserved_check.add("HOME")
    for key in extra_env:
        if key in reserved_check:
            return _err_spawn(
                "ErrReservedEnvKey",
                f"extra_env key {key!r} is reserved by claude-spawn and may not be overridden",
            )

    # ErrReservedEnvKey — claude_status_labels keys must not collide with reserved labels
    for key in claude_status_labels:
        if key.upper() in _RESERVED_LABEL_KEYS:
            return _err_spawn(
                "ErrReservedEnvKey",
                f"claude_status_labels key {key!r} is reserved by claude-spawn"
                " and may not be overridden",
            )

    # ErrInstanceIdCollision — only when caller explicitly supplied instance_id
    if caller_supplied_instance_id:
        cs_result = claude_status.workers(label="claude_spawn_owned=1")
        if not cs_result["ok"]:
            return _err_spawn(cs_result["err_name"], cs_result["err_description"])
        active_ids = {
            rec["instance_id"]
            for rec in cs_result["workers"].get("workers", [])
        }
        if instance_id in active_ids:
            return _err_spawn(
                "ErrInstanceIdCollision",
                f"instance_id {instance_id!r} is already in use by an active worker",
            )

    # --- SR-1.3 defaults for scalar params (post-validation) ---
    if instance_id is None:
        instance_id = str(uuid.uuid4())
    if tmux_session_name is None:
        tmux_session_name = f"{_sanitize_folder_name(cwd)}-{instance_id[:8]}"

    # --- SR-4.5 settings overlay synthesis ---
    effective_settings_path = _resolve_settings_path(permissions, claude_settings)
    if isinstance(effective_settings_path, dict):
        return effective_settings_path  # ErrClaudeSettingsMalformed

    # --- SR-4.1–4.4 tmux launch composition ---

    env_args: list[str] = []

    # SR-4.2 unconditional env vars
    for key, val in [
        ("CLAUDE_STATUS_INSTANCE_ID", instance_id),
        ("CLAUDE_STATUS_RELAY_MODE", "on"),
        ("CLAUDE_STATUS_AUQ_MODE", "record"),
        ("CLAUDE_STATUS_LABEL_CLAUDE_SPAWN_OWNED", "1"),
        ("CLAUDE_STATUS_LABEL_CLAUDE_SPAWN_SESSION_NAME", tmux_session_name),
        ("CLAUDE_STATUS_LABEL_CLAUDE_SPAWN_CWD", expanded_cwd),
    ]:
        env_args += ["-e", f"{key}={val}"]

    # SR-4.2 conditional model label
    if model:
        env_args += ["-e", f"CLAUDE_STATUS_LABEL_CLAUDE_SPAWN_MODEL={model.lower()}"]

    # extra_env pass-through
    for key, val in extra_env.items():
        env_args += ["-e", f"{key}={val}"]

    # claude_status_labels as CLAUDE_STATUS_LABEL_<UPPER>=<val>
    for key, val in claude_status_labels.items():
        env_args += ["-e", f"CLAUDE_STATUS_LABEL_{key.upper()}={val}"]

    # HOME override
    if claude_home:
        env_args += ["-e", f"HOME={claude_home}"]

    _stdout, stderr, rc = _tmux(
        ["new-session", "-d", "-s", tmux_session_name, "-c", expanded_cwd, *env_args]
    )
    if rc != 0:
        return {
            "ok": False,
            "operation": "spawn_worker",
            "err_name": "ErrTmuxSessionCreate",
            "err_description": stderr.strip() or "tmux new-session failed",
        }

    # Build send-keys command line
    cmd_parts = ["claude"]
    if model:
        cmd_parts += ["--model", model]
    if thinking:
        cmd_parts += ["--effort", thinking]
    if effective_settings_path:
        cmd_parts += ["--settings", effective_settings_path]
    cmd_parts += claude_args

    _stdout2, stderr2, rc2 = _tmux(
        ["send-keys", "-t", f"{tmux_session_name}:0.0", " ".join(cmd_parts), "Enter"]
    )
    if rc2 != 0:
        return {
            "ok": False,
            "operation": "spawn_worker",
            "err_name": "ErrTmuxSendKeys",
            "err_description": stderr2.strip() or "tmux send-keys failed",
        }

    # --- SR-5: readiness polling loop ---
    # Poll Claude Status until the spawned instance_id appears in the workers list,
    # or until the deadline expires.  Interleave tmux has-session probes to detect
    # early worker exit.  On cs failure, treat as a missed poll and retry until
    # timeout rather than short-circuiting — cs may be transiently unavailable.
    deadline = time.monotonic() + _SPAWN_READINESS_TIMEOUT
    poll_interval = 0.1  # seconds (~100 ms per SR-5 latency target)

    while time.monotonic() < deadline:
        # SR-5 / SR-10.1: match solely on instance_id
        cs_result = claude_status.workers(label="claude_spawn_owned=1")
        if cs_result.get("ok") is not False:
            for rec in cs_result["workers"].get("workers", []):
                if rec.get("instance_id") == instance_id:
                    return {"instance_id": instance_id, "tmux_session_name": tmux_session_name}

        # SR-5.4: detect worker exited before registering
        _stdout_hs, _stderr_hs, rc_hs = _tmux(["has-session", "-t", tmux_session_name])
        if rc_hs != 0:
            # Session is gone — best-effort pane capture for diagnostics
            try:
                cap_stdout, _cap_stderr, cap_rc = _tmux(
                    ["capture-pane", "-p", "-t", f"{tmux_session_name}:0.0", "-S", "-100"]
                )
                captured = cap_stdout if cap_rc == 0 else ""
            except Exception:
                captured = ""
            return _err_spawn(
                "ErrSpawnWorkerExitedEarly",
                f"worker {tmux_session_name!r} exited before registering with Claude Status."
                f" captured pane:\n{captured}",
            )

        time.sleep(poll_interval)

    # SR-5.3: timeout — best-effort kill; kill failure must NOT change err_name
    try:
        _tmux(["kill-session", "-t", tmux_session_name])
    except Exception:
        pass

    return _err_spawn(
        "ErrSpawnReadinessTimeout",
        f"worker {tmux_session_name!r} did not register with Claude Status"
        f" within {_SPAWN_READINESS_TIMEOUT}s",
    )


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

_WS_RE = re.compile(r"\s+")


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

    Returns ``{"workers": [{instance_id, session_name, cwd}, ...]}`` on success or
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
            "cwd": labels.get("claude_spawn_cwd", ""),
        })

    for skipped in envelope.get("skipped", []):
        iid = skipped.get("instance_id", "<unknown>") if isinstance(skipped, dict) else repr(skipped)
        print(
            f"list_spawned_workers: skipped row instance_id={iid!r}",
            file=sys.stderr,
        )

    return {"workers": projected}
