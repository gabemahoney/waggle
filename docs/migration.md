# Migration: Daemon → Stdio MCP

This document walks an operator from a working prior installation (HTTP daemon + SQLite) to Claude Spawn (stateless stdio MCP + Claude Status). There is **no in-place upgrade path** — this is a hard cutover.

## What changed

| Prior distribution | Claude Spawn |
|-----------|-----------|
| HTTP daemon (uvicorn, Starlette) | stdio MCP subprocess |
| SQLite state database | Claude Status (external CLI) |
| daemon entry-point subcommand | `claude-spawn mcp` |
| removed daemon-era subcommands for serve / state mutation / permission relay / question relay | Removed — Claude Status handles state |
| `register_caller`, `list_workers`, `check_status`, `approve_permission` MCP tools | Removed — use `claude-status` CLI directly |
| `spawn_worker`, `send_input`, `get_output`, `terminate_worker`, `answer_question` | Retained, redesigned |
| `list_spawned_workers` (new) | Added |

## Step 1: Stop the old daemon

Stop and disable the prior daemon's systemd user service. The unit name matches whatever the earlier distribution installed:

```bash
systemctl --user stop <prior-unit>
systemctl --user disable <prior-unit>
```

Remove the service file and reload the daemon:

```bash
rm -f <prior-unit-file>
systemctl --user daemon-reload
```

These paths existed only under the earlier distribution; Claude Spawn does not install a systemd unit.

## Step 2: Remove old daemon hooks from Claude settings

Edit `~/.claude/settings.json` and remove all hook entries that reference the prior daemon's hooks (the earlier distribution installed hooks for state mutation, permission relay, and question relay). The new `claude-spawn install` command will write the replacement hooks.

## Step 3: Delete the old database

The SQLite database is no longer used. Delete the daemon's state directory under `$HOME`. Its name was the prior distribution's tool name prefixed with a dot — substitute that name below:

```bash
rm -rf ~/.<prior-tool-name>/
```

## Step 4: Install the new package

```bash
cd /path/to/claude-spawn  # your clone of this repo
pip install .              # or: poetry install
```

## Step 5: Install Claude Status

Install the `claude-status` binary on PATH. See the [Claude Status README](https://github.com/anthropics/claude-status) for platform-specific instructions.

Verify:

```bash
claude-status capabilities
```

## Step 6: Wire hooks

```bash
claude-spawn install
```

This runs `claude-status install-hooks` with the relay and AUQ mode settings Claude Spawn requires. Optionally pass `--auq-order` to control hook ordering:

```bash
claude-spawn install --auq-order before:other-hook
```

Verify health:

```bash
claude-spawn sting
```

## Step 7: Register the new MCP server with Claude Code

If you had the prior distribution registered as an MCP server, remove that registration first. The registration name was whatever you chose when running `claude mcp add`; substitute it below:

```bash
claude mcp remove <prior-registration-name> 2>/dev/null || true
```

Add the new stdio transport:

```bash
claude mcp add --transport stdio claude-spawn claude-spawn mcp
```

Verify:

```bash
claude mcp list
```

## Step 8: Restart Claude Code

Restart any Claude Code sessions that should use the new Claude Spawn.

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
3. Restore the daemon's state directory from backup if needed
4. Re-register the prior daemon as a systemd user service
5. Remove the new stdio MCP registration and re-add the HTTP one
