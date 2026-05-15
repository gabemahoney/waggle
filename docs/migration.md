# Migration: Daemon → Stdio MCP

This document walks an operator from a working old-Waggle installation (HTTP daemon + SQLite) to the new Waggle (stateless stdio MCP + Claude Status). There is **no in-place upgrade path** — this is a hard cutover.

## What changed

| Old Waggle | New Waggle |
|-----------|-----------|
| HTTP daemon (uvicorn, Starlette) | stdio MCP subprocess |
| SQLite state database | Claude Status (external CLI) |
| `waggle serve` | `waggle mcp` |
| `waggle set-state`, `waggle permission-request`, `waggle ask-relay` | Removed — Claude Status handles state |
| `register_caller`, `list_workers`, `check_status`, `approve_permission` MCP tools | Removed — use `claude-status` CLI directly |
| `spawn_worker`, `send_input`, `get_output`, `terminate_worker`, `answer_question` | Retained, redesigned |
| `list_spawned_workers` (new) | Added |

## Step 1: Stop the old daemon

```bash
systemctl --user stop waggle
systemctl --user disable waggle
```

Remove the service file:

```bash
rm -f ~/.config/systemd/user/waggle.service
systemctl --user daemon-reload
```

## Step 2: Remove old waggle hooks from Claude settings

Edit `~/.claude/settings.json` and remove all hook entries that reference `waggle set-state`, `waggle permission-request`, or `waggle ask-relay`. The new `waggle install` command will write the replacement hooks.

## Step 3: Delete the old database

The SQLite database is no longer used. You can delete it:

```bash
rm -rf ~/.waggle/
```

## Step 4: Install the new package

```bash
cd /path/to/waggle   # your clone of this repo
pip install .        # or: poetry install
```

## Step 5: Install Claude Status

Install the `claude-status` binary on PATH. See the [Claude Status README](https://github.com/anthropics/claude-status) for platform-specific instructions.

Verify:

```bash
claude-status capabilities
```

## Step 6: Wire hooks

```bash
waggle install
```

This runs `claude-status install-hooks` with the relay and AUQ mode settings Waggle requires. Optionally pass `--auq-order` to control hook ordering:

```bash
waggle install --auq-order before:other-hook
```

Verify health:

```bash
waggle sting
```

## Step 7: Register the new MCP server with Claude Code

Remove the old HTTP transport registration first (if present):

```bash
claude mcp remove waggle 2>/dev/null || true
```

Add the new stdio transport:

```bash
claude mcp add --transport stdio waggle waggle mcp
```

Verify:

```bash
claude mcp list
```

## Step 8: Restart Claude Code

Restart any Claude Code sessions that should use the new Waggle.

## Step 9: Smoke test

In an orchestrator Claude session, call the six surviving tools:

1. `spawn_worker` — verify `instance_id` and `session_name` are returned
2. `list_spawned_workers` — verify the new worker appears
3. `get_output` — verify pane content is returned
4. `send_input` — send text to the worker pane
5. `answer_question` — answer a pending question (if applicable)
6. `terminate_worker` — kill the worker's tmux session

For state reads and permission approval that the old `check_status` and `approve_permission` tools handled, use `claude-status` directly:

```bash
claude-status worker <instance_id>       # full worker state
claude-status decide <instance_id> allow # approve a pending permission
claude-status decide <instance_id> deny  # deny a pending permission
```

## Rollback

There is no automated rollback. If you need to revert:

1. Check out the previous release tag
2. Re-install the old package
3. Restore `~/.waggle/` from backup if needed
4. Re-register `waggle serve` as a systemd user service
5. Remove the new stdio MCP registration and re-add the HTTP one
