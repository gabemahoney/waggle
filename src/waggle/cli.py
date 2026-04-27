import argparse
import json
import subprocess
import sys


class WaggleArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        print(json.dumps({"status": "error", "message": message}))
        sys.exit(2)


def _handle_set_state(args):
    """Update worker state from tmux pane content, or delete the worker row."""
    try:
        result = subprocess.run(
            ["tmux", "show-environment", "WAGGLE_WORKER_ID"],
            capture_output=True, text=True
        )
        output = result.stdout.strip()
        if not output or output.startswith("-") or "=" not in output:
            sys.exit(0)
        worker_id = output.split("=", 1)[1]
        if not worker_id:
            sys.exit(0)
    except Exception:
        sys.exit(0)

    try:
        from waggle import config, database

        db_path = config.get_db_path()

        if args.delete:
            with database.connection(db_path) as conn:
                conn.execute("DELETE FROM workers WHERE worker_id = ?", (worker_id,))
            sys.exit(0)

        with database.connection(db_path) as conn:
            row = conn.execute(
                "SELECT session_id FROM workers WHERE worker_id = ?", (worker_id,)
            ).fetchone()
        if row is None:
            sys.exit(0)
        session_id = row["session_id"]

        from waggle.tmux import _capture_pane_sync
        capture = _capture_pane_sync(session_id, None, 200)
        if capture.get("status") != "success":
            sys.exit(0)
        content = capture["content"]

        from waggle import state_parser
        state, _prompt_data = state_parser.parse(content)
        if state == "unknown":
            state = "done"

        with database.connection(db_path) as conn:
            conn.execute(
                "UPDATE workers SET status = ?, output = ?, updated_at = CURRENT_TIMESTAMP"
                " WHERE worker_id = ?",
                (state, content, worker_id),
            )
    except Exception:
        pass

    sys.exit(0)


def main():
    parser = WaggleArgumentParser(
        description="Waggle - HTTP daemon for managing Claude Code worker agents",
        prog="waggle"
    )
    subparsers = parser.add_subparsers(dest="subcommand")

    # waggle serve
    subparsers.add_parser(
        "serve",
        help="Start the Waggle HTTP daemon",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Start the Waggle HTTP daemon (Uvicorn + FastMCP)"
    )

    # waggle set-state
    set_state_parser = subparsers.add_parser(
        "set-state",
        help="Update worker state from tmux pane content",
    )
    set_state_parser.add_argument("--delete", action="store_true", help="Remove the worker row (SessionEnd)")

    # waggle sting
    subparsers.add_parser(
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
        import waggle.daemon
        waggle.daemon.run()
    elif args.subcommand == "set-state":
        _handle_set_state(args)
    elif args.subcommand == "sting":
        from waggle.sting import handle_sting
        handle_sting(args)
