"""claude-spawn sting — Claude Status health check."""

import sys


def check_claude_status_health() -> tuple[bool, str]:
    """Check Claude Status availability and contract version.

    Returns ``(healthy: bool, message: str)``.

    Green conditions (all three must hold):
      (a) ``claude-status`` is on PATH (ErrClaudeStatusNotFound → red)
      (b) The ``capabilities`` call succeeds (any other error → red)
      (c) ``contract_version`` major is 1 (ErrContractVersionMismatch → red)

    Uses ``claude_spawn.claude_status.capabilities()`` which handles (a) and (c)
    automatically; a returned ``ok=True`` means all three conditions are met.
    """
    from claude_spawn import claude_status

    result = claude_status.capabilities()
    if result["ok"]:
        cv = result["capabilities"].get("contract_version", "?")
        return True, f"claude-status OK (contract_version={cv})"

    err_name = result["err_name"]
    err_desc = result["err_description"]

    if err_name == "ErrClaudeStatusNotFound":
        return False, (
            "claude-status not found on PATH. "
            "Install claude-status and run 'claude-spawn install'."
        )
    if err_name == "ErrContractVersionMismatch":
        return False, f"contract_version mismatch: {err_desc}"
    return False, f"{err_name}: {err_desc}"


def handle_sting(args):
    """Handle the ``claude-spawn sting`` command.

    Exits 0 (green) when claude-status is reachable and contract_version
    major is 1; exits 1 (red) with an actionable error message otherwise.
    """
    healthy, message = check_claude_status_health()
    if healthy:
        print(message)
        sys.exit(0)
    print(f"ERROR: {message}", file=sys.stderr)
    sys.exit(1)
