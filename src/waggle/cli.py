import argparse
import json
import re
import sys

_SHELL_INJECT_RE = re.compile(r'[;&|`$(){}\\<>\'"!]')


def _safe_model(value):
    """Reject model names containing shell metacharacters."""
    if _SHELL_INJECT_RE.search(value):
        raise argparse.ArgumentTypeError(f"Invalid model name: {value!r}")
    return value


class WaggleArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        print(json.dumps({"status": "error", "message": message}))
        sys.exit(2)


def main():
    parser = WaggleArgumentParser(
        description="Waggle - Claude agent lifecycle manager",
        prog="waggle"
    )
    subparsers = parser.add_subparsers(dest="subcommand")

    # waggle serve
    subparsers.add_parser(
        "serve",
        help="Start the Waggle MCP server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Start the Waggle MCP server (stdio transport)"
    )

    # waggle list-agents
    list_agents_parser = subparsers.add_parser(
        "list-agents",
        help="List active waggle agents",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="List all active async agents with their status"
    )
    list_agents_parser.add_argument("--name", help="Filter by session name")
    list_agents_parser.add_argument("--repo", help="Filter by repo path substring (case-insensitive)")

    # waggle delete-repo-agents
    delete_parser = subparsers.add_parser(
        "delete-repo-agents",
        help="Delete all agent state for a repository",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Delete all agent state for a specific repository"
    )
    delete_parser.add_argument("--repo-root", default=None, help="Repository root path (default: current directory)")

    # waggle spawn-agent
    spawn_parser = subparsers.add_parser(
        "spawn-agent",
        help="Spawn an agent in a tmux session",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Launch a Claude or OpenCode agent in a tmux session"
    )
    spawn_parser.add_argument("--repo", required=True, help="Absolute path to repo directory")
    spawn_parser.add_argument("--session-name", required=True, help="tmux session name to create or reuse")
    spawn_parser.add_argument("--agent", required=True, choices=["claude", "opencode"], help="Agent type: claude or opencode")
    spawn_parser.add_argument("--model", type=_safe_model, help="Optional model name (e.g. sonnet, haiku, opus)")
    spawn_parser.add_argument("--command", help="Optional initial command to deliver after agent reaches ready state")
    spawn_parser.add_argument("--settings", help="Optional extra CLI flags (e.g. --dangerously-skip-permissions)")

    # waggle close-session
    close_parser = subparsers.add_parser(
        "close-session",
        help="Close an agent session",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Close an agent tmux session and remove its database entry"
    )
    close_parser.add_argument("--session-id", required=True, help="tmux session ID (e.g. $1)")
    close_parser.add_argument("--session-name", help="Optional session name to validate against")
    close_parser.add_argument("--force", action="store_true", help="Close even if an LLM agent is actively running")

    # waggle read-pane
    read_pane_parser = subparsers.add_parser(
        "read-pane",
        help="Read content from an agent's tmux pane",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Read pane content from a tmux session and detect agent state"
    )
    read_pane_parser.add_argument("--session-id", required=True, help="tmux session ID (e.g. $1)")
    read_pane_parser.add_argument("--pane-id", default=None, help="Pane ID (default: active pane)")
    read_pane_parser.add_argument("--scrollback", type=int, default=50, help="Lines of scrollback to capture (default: 50)")

    # waggle send-command
    send_cmd_parser = subparsers.add_parser(
        "send-command",
        help="Send a command to an agent's tmux pane",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Send a command or option number to a tmux session"
    )
    send_cmd_parser.add_argument("--session-id", required=True, help="tmux session ID (e.g. $1)")
    send_cmd_parser.add_argument("--command", required=True, help="Command text or option number to send")
    send_cmd_parser.add_argument("--pane-id", default=None, help="Pane ID (default: active pane)")
    send_cmd_parser.add_argument("--custom-text", default=None, help="Free-form text for 'Type something.' option")

    # waggle sting
    sting_parser = subparsers.add_parser(
        "sting",
        help="Emit waggle CLI reference if waggle MCP is not configured",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Exit silently if waggle MCP is detected, otherwise print CLI reference"
    )

    args = parser.parse_args()

    if args.subcommand is None:
        parser.print_help()
        sys.exit(0)
    elif args.subcommand == "serve":
        import waggle.server
        waggle.server.run()
    elif args.subcommand == "list-agents":
        import asyncio
        import waggle.server
        result = asyncio.run(waggle.server.list_agents(name=args.name, repo=args.repo, ctx=None))
        print(json.dumps(result))
        sys.exit(0 if result.get("status") == "success" else 1)
    elif args.subcommand == "delete-repo-agents":
        import asyncio
        import os
        import waggle.server
        repo_root = args.repo_root if args.repo_root else os.getcwd()
        result = asyncio.run(waggle.server.delete_repo_agents(repo_root=repo_root, ctx=None))
        print(json.dumps(result))
        sys.exit(0 if result.get("status") == "success" else 1)
    elif args.subcommand == "spawn-agent":
        import asyncio
        import waggle.server
        result = asyncio.run(waggle.server.spawn_agent(
            args.repo, args.session_name, args.agent,
            model=args.model, command=args.command, settings=args.settings, ctx=None
        ))
        print(json.dumps(result))
        sys.exit(0 if result.get("status") == "success" else 1)
    elif args.subcommand == "close-session":
        import asyncio
        import waggle.server
        result = asyncio.run(waggle.server.close_session(
            args.session_id, session_name=args.session_name, force=args.force
        ))
        print(json.dumps(result))
        sys.exit(0 if result.get("status") == "success" else 1)
    elif args.subcommand == "read-pane":
        import asyncio
        import waggle.server
        result = asyncio.run(waggle.server.read_pane(args.session_id, args.pane_id, args.scrollback))
        print(json.dumps(result))
        sys.exit(0 if result.get("status") == "success" else 1)
    elif args.subcommand == "send-command":
        import asyncio
        import waggle.server
        result = asyncio.run(waggle.server.send_command(args.session_id, args.command, args.pane_id, args.custom_text))
        print(json.dumps(result))
        sys.exit(0 if result.get("status") == "success" else 1)
    elif args.subcommand == "sting":
        from waggle.sting import handle_sting
        handle_sting(args)
