import argparse
import builtins
import json
import sys


class ClaudeSpawnArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        print(json.dumps({"status": "error", "message": message}))
        sys.exit(2)


def _parse_kv(s: str) -> tuple[str, str]:
    """Parse a KEY=VALUE string into a (key, value) tuple."""
    if "=" not in s:
        raise argparse.ArgumentTypeError(f"expected KEY=VALUE, got {s!r}")
    k, _, v = s.partition("=")
    return k, v


def _interactive_write_template(name: str, force: bool) -> dict:
    """Interactively prompt for template options.

    Returns write_template_impl result dict, or a cancellation dict.
    Raises SystemExit(1) on cancellation.
    """
    from claude_spawn.templates import load_template

    # Load existing template values for hint display
    existing = {}
    load_result = load_template(name)
    if load_result.get("ok") is True:
        existing = load_result["load_template"]

    def prompt(field: str, description: str, current=None) -> str | None:
        hint = f" [current: {current!r}]" if current is not None else ""
        print(f"{field} — {description}{hint} (skip to leave unset):", file=sys.stderr)
        return builtins.input("> ").strip()

    def prompt_list(field: str, description: str, current=None) -> list[str] | None:
        hint = f" [current: {current!r}]" if current is not None else ""
        print(
            f"{field} — {description}{hint}\n"
            "  Enter one value per line; blank line to finish (skip to leave unset):",
            file=sys.stderr,
        )
        items = []
        while True:
            line = builtins.input("> ").strip()
            if line == "":
                break
            if line == "skip":
                return None
            items.append(line)
        return items if items else None

    def prompt_map(field: str, description: str, current=None) -> dict[str, str] | None:
        hint = f" [current: {current!r}]" if current is not None else ""
        print(
            f"{field} — {description}{hint}\n"
            "  Enter KEY=VALUE per line; blank line to finish (skip to leave unset):",
            file=sys.stderr,
        )
        result = {}
        while True:
            line = builtins.input("> ").strip()
            if line == "":
                break
            if line == "skip":
                return None
            if "=" not in line:
                print("  (expected KEY=VALUE — try again)", file=sys.stderr)
                continue
            k, _, v = line.partition("=")
            result[k] = v
        return result if result else None

    options: dict = {}

    # Scalar options
    scalar_fields = [
        ("cwd", "Working directory for the spawned agent"),
        ("model", "Claude model identifier (e.g. claude-opus-4-5)"),
        ("thinking", "Thinking level: low, medium, high, or xhigh"),
        ("tmux_session_name", "Tmux session name to use"),
        ("instance_id", "Unique instance identifier"),
        ("claude_home", "Path to Claude home directory"),
        ("claude_settings", "Path to Claude settings file"),
    ]
    for field, desc in scalar_fields:
        current = existing.get(field)
        val = prompt(field, desc, current)
        if val and val != "skip":
            options[field] = val

    # claude_args (list)
    current_args = existing.get("claude_args")
    vals = prompt_list("claude_args", "Extra arguments passed to claude CLI", current_args)
    if vals is not None:
        options["claude_args"] = vals

    # extra_env (map)
    current_env = existing.get("extra_env")
    env_map = prompt_map("extra_env", "Extra environment variables (KEY=VALUE)", current_env)
    if env_map is not None:
        options["extra_env"] = env_map

    # claude_status_labels (map)
    current_labels = existing.get("claude_status_labels")
    labels_map = prompt_map(
        "claude_status_labels",
        "Labels for claude-status reporting (KEY=VALUE)",
        current_labels,
    )
    if labels_map is not None:
        options["claude_status_labels"] = labels_map

    # permissions sub-dict
    permissions: dict[str, list[str]] = {}
    current_perms = existing.get("permissions", {})

    for perm_key, desc in [
        ("allow", "Permission allow patterns (tool/path globs)"),
        ("deny", "Permission deny patterns"),
        ("ask", "Permission ask patterns"),
    ]:
        current_perm = current_perms.get(perm_key) if current_perms else None
        vals = prompt_list(f"permissions.{perm_key}", desc, current_perm)
        if vals is not None:
            permissions[perm_key] = vals

    if permissions:
        options["permissions"] = permissions

    from claude_spawn.templates import write_template_impl
    return write_template_impl(name, options, force=force)


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

    # claude-spawn write-template
    wt_parser = subparsers.add_parser(
        "write-template",
        help="Write (create or overwrite) a spawn template file",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=(
            "Write a .toml template file for use with claude-spawn. "
            "Delegates to write_template_impl for all validation and writes."
        ),
    )
    wt_parser.add_argument(
        "name",
        help="Template name (filename stem, e.g. 'my-agent').",
    )

    # Mutually exclusive group: --interactive vs option flags
    # We use a simple flag and enforce the mutual exclusion in dispatch logic,
    # since argparse cannot natively express "either --interactive OR any of N flags".
    wt_parser.add_argument(
        "--interactive",
        action="store_true",
        default=False,
        help="Interactively prompt for each option. Mutually exclusive with option flags.",
    )

    # Scalar option flags (SR-1.1)
    wt_parser.add_argument(
        "--cwd",
        default=None,
        help="Working directory for the spawned agent (SR-1.1: cwd).",
    )
    wt_parser.add_argument(
        "--model",
        default=None,
        help="Claude model identifier (SR-1.1: model).",
    )
    wt_parser.add_argument(
        "--thinking",
        default=None,
        help="Thinking level: low, medium, high, or xhigh (SR-1.1: thinking). "
             "No enum validation at CLI layer.",
    )
    wt_parser.add_argument(
        "--tmux-session-name",
        dest="tmux_session_name",
        default=None,
        help="Tmux session name (SR-1.1: tmux_session_name).",
    )
    wt_parser.add_argument(
        "--instance-id",
        dest="instance_id",
        default=None,
        help="Unique instance identifier (SR-1.1: instance_id).",
    )
    wt_parser.add_argument(
        "--claude-home",
        dest="claude_home",
        default=None,
        help="Path to Claude home directory (SR-1.1: claude_home).",
    )
    wt_parser.add_argument(
        "--claude-settings",
        dest="claude_settings",
        default=None,
        help="Path to Claude settings file (SR-1.1: claude_settings).",
    )

    # Repeatable list flag
    wt_parser.add_argument(
        "--claude-arg",
        dest="claude_args",
        action="append",
        metavar="VALUE",
        default=None,
        help="Extra argument passed to the claude CLI (repeatable; SR-1.1: claude_args).",
    )

    # Repeatable KEY=VALUE map flags
    wt_parser.add_argument(
        "--extra-env-entry",
        dest="extra_env_entries",
        action="append",
        metavar="KEY=VALUE",
        type=_parse_kv,
        default=None,
        help="Extra environment variable entry KEY=VALUE (repeatable; SR-1.1: extra_env).",
    )
    wt_parser.add_argument(
        "--claude-status-labels-entry",
        dest="claude_status_labels_entries",
        action="append",
        metavar="KEY=VALUE",
        type=_parse_kv,
        default=None,
        help="Claude-status label entry KEY=VALUE (repeatable; SR-1.1: claude_status_labels).",
    )

    # Repeatable permission-list flags
    wt_parser.add_argument(
        "--permissions-allow",
        dest="permissions_allow",
        action="append",
        metavar="PATTERN",
        default=None,
        help="Permission allow pattern (repeatable; SR-1.1: permissions.allow).",
    )
    wt_parser.add_argument(
        "--permissions-deny",
        dest="permissions_deny",
        action="append",
        metavar="PATTERN",
        default=None,
        help="Permission deny pattern (repeatable; SR-1.1: permissions.deny).",
    )
    wt_parser.add_argument(
        "--permissions-ask",
        dest="permissions_ask",
        action="append",
        metavar="PATTERN",
        default=None,
        help="Permission ask pattern (repeatable; SR-1.1: permissions.ask).",
    )

    # Force flag
    wt_parser.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="Overwrite an existing template. Default: error if template already exists.",
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
    elif args.subcommand == "write-template":
        # Determine which option flags were supplied (non-None / non-empty)
        _option_flag_attrs = [
            "cwd", "model", "thinking", "tmux_session_name", "instance_id",
            "claude_home", "claude_settings", "claude_args",
            "extra_env_entries", "claude_status_labels_entries",
            "permissions_allow", "permissions_deny", "permissions_ask",
        ]
        any_option_flag = any(
            getattr(args, attr) not in (None, False, [])
            for attr in _option_flag_attrs
        )

        if args.interactive and any_option_flag:
            wt_parser.error("--interactive cannot be combined with option flags")

        if args.interactive:
            try:
                result = _interactive_write_template(args.name, args.force)
            except (EOFError, KeyboardInterrupt):
                print(json.dumps({"status": "error", "message": "write-template cancelled"}))
                sys.exit(1)
        else:
            # Build options dict from flags — only include supplied keys
            options: dict = {}

            if args.cwd is not None:
                options["cwd"] = args.cwd
            if args.model is not None:
                options["model"] = args.model
            if args.thinking is not None:
                options["thinking"] = args.thinking
            if args.tmux_session_name is not None:
                options["tmux_session_name"] = args.tmux_session_name
            if args.instance_id is not None:
                options["instance_id"] = args.instance_id
            if args.claude_home is not None:
                options["claude_home"] = args.claude_home
            if args.claude_settings is not None:
                options["claude_settings"] = args.claude_settings
            if args.claude_args is not None:
                options["claude_args"] = args.claude_args
            if args.extra_env_entries is not None:
                options["extra_env"] = dict(args.extra_env_entries)
            if args.claude_status_labels_entries is not None:
                options["claude_status_labels"] = dict(args.claude_status_labels_entries)

            permissions: dict[str, list[str]] = {}
            if args.permissions_allow is not None:
                permissions["allow"] = args.permissions_allow
            if args.permissions_deny is not None:
                permissions["deny"] = args.permissions_deny
            if args.permissions_ask is not None:
                permissions["ask"] = args.permissions_ask
            if permissions:
                options["permissions"] = permissions

            from claude_spawn.templates import write_template_impl
            result = write_template_impl(args.name, options, force=args.force)

        print(json.dumps(result))
        sys.exit(0 if result.get("ok") is True else 2)
