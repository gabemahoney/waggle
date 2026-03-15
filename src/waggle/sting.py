"""waggle sting — emits CLI reference in non-MCP sessions."""

import json
import re
import sys
from pathlib import Path

# Matches "waggle", "waggle-mcp", "my_waggle", "WAGGLE" but NOT "wagglefish" or "mywaggle"
_WAGGLE_PATTERN = re.compile(r"(?i)(?:^|[-_])waggle(?:$|[-_])")

_CLI_REFERENCE = """\
waggle is a CLI tool for managing Claude agent lifecycles via tmux.
All subcommands output JSON to stdout. Exit 0 on success, exit 1 on error, exit 2 on usage error.
Run waggle <command> --help for full usage on any command.

  serve                 Start the waggle MCP server (stdio transport)
  list-agents           List active waggle agents with their status
  spawn-agent           Spawn a Claude or OpenCode agent in a tmux session
  close-session         Close an agent session and remove its database entry
  delete-repo-agents    Delete all agent state for a repository
  read-pane             Read content from an agent's tmux pane and detect agent state
  send-command          Send a command or option number to an agent's tmux pane
  sting                 Emit this CLI reference if waggle MCP is not configured"""


def _key_matches_waggle(key: str) -> bool:
    return bool(_WAGGLE_PATTERN.search(key))


def _has_waggle_in_mcp_servers(mcp_servers: object) -> bool:
    if not isinstance(mcp_servers, dict):
        return False
    return any(_key_matches_waggle(k) for k in mcp_servers)


def _detect_mcp() -> bool:
    """Scan ~/.claude.json and ~/.claude/settings.json for waggle MCP entry."""
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


def handle_sting(args):
    """Handle the `waggle sting` command."""
    if _detect_mcp():
        sys.exit(0)
    print(_CLI_REFERENCE)
    sys.exit(0)
