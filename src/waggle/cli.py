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

    args = parser.parse_args()

    if args.subcommand is None:
        parser.print_help()
        sys.exit(0)
    elif args.subcommand == "serve":
        import waggle.server
        waggle.server.run()
