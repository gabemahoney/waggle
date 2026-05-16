import argparse
import json
import sys


class ClaudeSpawnArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        print(json.dumps({"status": "error", "message": message}))
        sys.exit(2)


def main():
    parser = ClaudeSpawnArgumentParser(
        description="Claude Spawn - stateless stdio MCP server for Claude Code worker agents",
        prog="claude-spawn"
    )
    subparsers = parser.add_subparsers(dest="subcommand")

    # claude-spawn sting
    subparsers.add_parser(
        "sting",
        help="Health-check the claude-status dependency",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Exit 0 if claude-status is reachable and its contract_version major is 1; exit 1 otherwise"
    )

    # claude-spawn mcp
    subparsers.add_parser(
        "mcp",
        help="Launch the Claude Spawn stdio MCP server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Start the Claude Spawn stdio MCP server. Reads from stdin, writes to stdout.",
    )

    # claude-spawn install
    install_parser = subparsers.add_parser(
        "install",
        help="Install Claude Status hooks and wire Claude Spawn's env vars",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=(
            "Verify claude-status is on PATH and run 'claude-status install-hooks' "
            "with CLAUDE_STATUS_RELAY_MODE=on and CLAUDE_STATUS_AUQ_MODE=record."
        ),
    )
    install_parser.add_argument(
        "--auq-order",
        dest="auq_order",
        default=None,
        help="Forwarded to 'claude-status install-hooks --auq-order'. "
             "E.g. 'before:<other>', 'after:<other>', or 'last'.",
    )

    args = parser.parse_args()

    if args.subcommand is None:
        parser.print_help()
        sys.exit(0)
    elif args.subcommand == "sting":
        from claude_spawn.sting import handle_sting
        handle_sting(args)
    elif args.subcommand == "mcp":
        from claude_spawn.mcp_stdio import run
        run()
    elif args.subcommand == "install":
        from claude_spawn.installer import handle_install
        handle_install(args)
