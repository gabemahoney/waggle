# Waggle v1 → v2 Migration Guide

## What Changed

### Architecture
| Aspect | v1 | v2 |
|--------|----|----|
| MCP transport | `stdio` (subprocess) | HTTP (`http://localhost:8422/mcp`) |
| Hook scripts | Bash scripts in `~/.waggle/hooks/` | Python CLI commands (`waggle set-state`, etc.) |
| Process model | Spawned per-Claude-session | Persistent background daemon (systemd) |
| Remote access | Not supported | SSH-authenticated callers via `authorized_keys.json` |
| Job queue | None | Durable SQLite-backed queue with retry and expiry |
| PermissionRequest | Not handled | `waggle permission-request` relays to orchestrator |
| AskUserQuestion | Not handled | `waggle ask-relay` relays to orchestrator |

### Hook commands
v1 hooks called `~/.waggle/hooks/waggle_set_state.sh`. v2 hooks call the `waggle` Python CLI directly — no bash wrapper scripts, no `~/.waggle/hooks/` directory.

### MCP registration
v1: `claude mcp add --transport stdio waggle -- poetry run waggle serve`
v2: `claude mcp add --transport http waggle http://localhost:8422/mcp` (daemon must already be running)

---

## Upgrade Steps

### 1. Uninstall v1

```bash
./install.sh --uninstall
```

This stops the process, removes hooks from `~/.claude/settings.json`, and prints a reminder to run:

```bash
claude mcp remove waggle
```

Run that command.

### 2. Pull and install v2

```bash
git pull
./install.sh
```

The installer:
- Runs `poetry install` (or `pip install -e .` if poetry is absent)
- Deploys `waggle.service` to `~/.config/systemd/user/`
- Enables and starts the daemon via systemctl
- Merges v2 hooks into `~/.claude/settings.json`

### 3. Register the HTTP MCP server

The installer prints this command — run it once:

```bash
claude mcp add --transport http waggle http://localhost:8422/mcp
```

Verify:

```bash
claude mcp list
```

### 4. Configure remote access (optional)

To allow remote CMA callers, create `~/.waggle/authorized_keys.json`:

```json
[
  {
    "name": "my-cma-caller",
    "public_key": "ssh-ed25519 AAAA..."
  }
]
```

---

## Database

There is no data migration. v2 uses a fresh database schema. If `~/.waggle/state.db` exists from v1, remove it:

```bash
rm -f ~/.waggle/state.db ~/.waggle/queue.db
```

The daemon recreates both on startup.

---

## Configuration

Create `~/.waggle/config.json` to override defaults. All keys are optional.

```json
{
  "database_path": "~/.waggle/state.db",
  "queue_path": "~/.waggle/queue.db",
  "max_workers": 8,
  "http_port": 8422,
  "repos_path": "~/.waggle/repos",
  "relay_timeout_seconds": 3600,
  "authorized_keys_path": "~/.waggle/authorized_keys.json",
  "admin_email": "",
  "admin_notify_after_retries": 5,
  "max_retry_hours": 72
}
```

Key new fields:
- `repos_path` — where remote repos are cloned
- `authorized_keys_path` — SSH public keys for remote callers
- `admin_email` — email for escalation after repeated worker failures
- `relay_timeout_seconds` — how long to wait for orchestrator to resolve a permission or ask-relay event (default 1 hour)

---

## Environment

Create `~/.waggle/env` for secrets (loaded by systemd, file may be absent):

```
WAGGLE_CMA_API_KEY=your-key-here
```

This key is used by waggle's CMA client to notify remote orchestrators of worker state changes.

---

## Verify the Daemon

```bash
systemctl --user status waggle
curl http://localhost:8422/mcp
```

If the service fails to start:

```bash
journalctl --user -u waggle -n 50
```
