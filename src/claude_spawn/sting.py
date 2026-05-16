"""claude-spawn sting — emits CLI reference in non-MCP sessions."""

import json
import re
import sys
from pathlib import Path

# Matches "waggle", "waggle-mcp", "my_waggle", "WAGGLE" but NOT "wagglefish" or "mywaggle"
_WAGGLE_PATTERN = re.compile(r"(?i)(?:^|[-_])waggle(?:$|[-_])")


def _key_matches_waggle(key: str) -> bool:
    return bool(_WAGGLE_PATTERN.search(key))


def _has_waggle_in_mcp_servers(mcp_servers: object) -> bool:
    if not isinstance(mcp_servers, dict):
        return False
    return any(_key_matches_waggle(k) for k in mcp_servers)


def _detect_mcp() -> bool:
    """Scan ~/.claude.json and ~/.claude/settings.json for claude-spawn MCP entry."""
    home = Path.home()

    # Location 1: ~/.claude.json top-level mcpServers
    claude_json = home / ".claude.json"
    try:
        data = json.loads(claude_json.read_text(encoding="utf-8"))
        if _has_waggle_in_mcp_servers(data.get("mcpServers")):
            return True
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass

    # Location 2: ~/.claude/settings.json top-level mcpServers
    settings_json = home / ".claude" / "settings.json"
    try:
        data = json.loads(settings_json.read_text(encoding="utf-8"))
        if _has_waggle_in_mcp_servers(data.get("mcpServers")):
            return True
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass

    return False


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
