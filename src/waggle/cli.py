import argparse
import json
import sys


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
    spawn_parser.add_argument("--model", help="Optional model name (e.g. sonnet, haiku, opus)")
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
