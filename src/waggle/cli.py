import argparse
import json
import subprocess
import sys
import time
import uuid


class WaggleArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        print(json.dumps({"status": "error", "message": message}))
        sys.exit(2)


def _handle_permission_request(args):
    """Handle PermissionRequest hook: relay to orchestrator and long-poll for decision."""
    try:
        # Read hook data from stdin
        hook_data = json.loads(sys.stdin.read())

        # Get worker_id from tmux env
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

        from waggle import config, database

        db_path = config.get_db_path()
        cfg = config.get_config()
        relay_timeout_seconds = int(cfg.get("relay_timeout_seconds", 3600))

        relay_id = str(uuid.uuid4())
        details = json.dumps({
            "tool_name": hook_data.get("tool_name", ""),
            "tool_input": hook_data.get("tool_input", {}),
        })

        with database.connection(db_path) as conn:
            conn.execute(
                """
                INSERT INTO pending_relays (relay_id, worker_id, relay_type, details, status)
                VALUES (?, ?, 'permission', ?, 'pending')
                """,
                (relay_id, worker_id, details),
            )
            conn.execute(
                "UPDATE workers SET status = 'check_permission' WHERE worker_id = ?",
                (worker_id,),
            )

        start = time.monotonic()
        while True:
            time.sleep(0.5)
            with database.connection(db_path) as conn:
                row = conn.execute(
                    "SELECT status, response FROM pending_relays WHERE relay_id = ?",
                    (relay_id,),
                ).fetchone()

            if row and row["status"] == "resolved":
                response = row["response"] or "deny"
                if response == "allow":
                    print(json.dumps({
                        "hookSpecificOutput": {
                            "hookEventName": "PermissionRequest",
                            "decision": {"behavior": "allow"},
                        }
                    }))
                else:
                    print(json.dumps({
                        "hookSpecificOutput": {
                            "hookEventName": "PermissionRequest",
                            "decision": {"behavior": "deny", "message": "Denied by orchestrator"},
                        }
                    }))
                sys.exit(0)

            if time.monotonic() - start > relay_timeout_seconds:
                with database.connection(db_path) as conn:
                    conn.execute(
                        "UPDATE pending_relays SET status = 'timeout' WHERE relay_id = ?",
                        (relay_id,),
                    )
                print(json.dumps({
                    "hookSpecificOutput": {
                        "hookEventName": "PermissionRequest",
                        "decision": {"behavior": "deny", "message": "Denied by orchestrator"},
                    }
                }))
                sys.exit(0)
    except Exception:
        sys.exit(0)


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

    # waggle permission-request
    subparsers.add_parser(
        "permission-request",
        help="Handle a PermissionRequest hook (reads JSON from stdin)",
    )

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
    elif args.subcommand == "permission-request":
        _handle_permission_request(args)
    elif args.subcommand == "set-state":
        _handle_set_state(args)
    elif args.subcommand == "sting":
        from waggle.sting import handle_sting
        handle_sting(args)
