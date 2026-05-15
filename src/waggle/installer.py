"""waggle install — wire Claude Status hooks for Waggle (SR-5.1, SR-5.2).

Verifies ``claude-status`` is on PATH, then delegates hook installation to
``claude-status install-hooks`` with the required env vars.  Forwards the
optional ``--auq-order`` flag so the operator can control hook ordering
during transition.

No module-level side effects.  Import is inert.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Subprocess seam — patch target: waggle.installer._run_install_hooks
# ---------------------------------------------------------------------------


def _run_install_hooks(argv: list[str], env: dict[str, str]) -> tuple[str, str, int]:
    """Run ``claude-status install-hooks <argv>`` with the given environment.

    Returns ``(stdout, stderr, returncode)``.  Never retries.
    """
    result = subprocess.run(
        ["claude-status", "install-hooks", *argv],
        env=env,
        capture_output=True,
        text=True,
    )
    return result.stdout, result.stderr, result.returncode


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def handle_install(args) -> None:
    """Handle the ``waggle install`` CLI subcommand.

    Exits 0 on success, exits 1 on failure with an actionable error message.
    """
    # SR-5.1 — verify claude-status is on PATH before doing anything else.
    if shutil.which("claude-status") is None:
        print(
            "ERROR: 'claude-status' not found on PATH.\n"
            "Install claude-status first, then re-run 'waggle install'.\n"
            "See: https://github.com/anthropics/claude-status for installation instructions.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Build env with required vars injected (inherit everything else).
    env = os.environ.copy()
    env["CLAUDE_STATUS_RELAY_MODE"] = "on"
    env["CLAUDE_STATUS_AUQ_MODE"] = "record"

    # Forward --auq-order if provided.
    extra_argv: list[str] = []
    auq_order = getattr(args, "auq_order", None)
    if auq_order:
        extra_argv += ["--auq-order", auq_order]

    stdout, stderr, rc = _run_install_hooks(extra_argv, env)

    if rc != 0:
        msg = stderr.strip() or stdout.strip() or "claude-status install-hooks failed"
        print(f"ERROR: {msg}", file=sys.stderr)
        sys.exit(1)

    if stdout.strip():
        print(stdout.strip())

    # SR-5.2 — remove the old Waggle hook template file if present.
    _remove_legacy_hook_template()

    sys.exit(0)


def _remove_legacy_hook_template() -> None:
    """Delete the old hooks/settings.json.template if it still exists."""
    template = Path("hooks") / "settings.json.template"
    try:
        template.unlink(missing_ok=True)
    except OSError:
        pass  # Best-effort; not fatal.
