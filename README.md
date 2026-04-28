# Waggle

HTTP daemon for managing Claude Code worker agents in tmux sessions.

## Overview

Waggle is a standalone HTTP daemon that lets LLM orchestrators spawn, monitor, and terminate Claude Code worker agents running in tmux sessions.

It exposes an MCP interface (via HTTP transport) for local orchestrators and a REST API for future remote access. It is **not** an stdio MCP subprocess — it runs as a persistent background service.

## Installation

**Dependencies:**
- tmux 3.2a+
- sqlite3
- python3

**Install Waggle:**

```bash
git clone https://github.com/gabemahoney/waggle.git
cd waggle
./install.sh
```

This installs Python dependencies, deploys the waggle systemd user service, and configures Claude hooks in `~/.claude/settings.json`.

## Quick Start

**1. Install**

```bash
git clone https://github.com/gabemahoney/waggle.git
cd waggle
./install.sh
```

The daemon starts automatically as a systemd user service. Verify:

```bash
systemctl --user status waggle
```

**2. Register the MCP server with Claude Code**

```bash
claude mcp add --transport http waggle http://localhost:8422/mcp
```

Verify:

```bash
claude mcp list
```

**3. Verify hooks**

`install.sh` automatically merges the following hooks into `~/.claude/settings.json`:

| Event | Command |
|-------|---------|
| `PermissionRequest` | `waggle permission-request` |
| `SessionStart` | `waggle set-state waiting` |
| `UserPromptSubmit` | `waggle set-state working` |
| `PreToolUse` (AskUserQuestion) | `waggle ask-relay` |
| `PreToolUse` (other tools) | `waggle set-state working` |
| `PostToolUse` | `waggle set-state working` |
| `Stop` | `waggle set-state waiting` |
| `SessionEnd` | `waggle set-state --delete` |

Restart Claude Code after installation.

## MCP Tools

### `register_caller`

Register this caller with waggle. Call once at the start of a session.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `caller_type` | `str` | No | `"local"` | `"local"` or `"cma"` |

**Returns:** `{"caller_id": str}`

---

### `spawn_worker`

Spawn a new Claude Code worker agent in a tmux session.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `model` | `str` | Yes | — | Claude model name (e.g. `"sonnet"`, `"haiku"`, `"opus"`) |
| `repo` | `str` | Yes | — | Local path or GitHub HTTPS URL |
| `session_name` | `str` | No | `None` | tmux session name; auto-generated as `waggle-{id[:8]}` if omitted |

**Returns:** `{"worker_id": str, "session_name": str}` or `{"error": str}`

**Errors:**
- `concurrency_limit_reached` — active worker count is at `max_workers`
- `repo_clone_failed` — git clone or fetch failed
- `invalid_repo` — URL cannot be parsed

---

### `list_workers`

List all workers belonging to this caller.

**Parameters:** none (caller scoped automatically via MCP session)

**Returns:**
```json
{
  "workers": [
    {
      "worker_id": "...",
      "caller_id": "...",
      "session_name": "waggle-abc12345",
      "session_id": "$1",
      "model": "sonnet",
      "repo": "/path/to/repo",
      "status": "working",
      "output": "...",
      "updated_at": "2026-04-27T12:00:00"
    }
  ]
}
```

---

### `check_status`

Check the current status of a specific worker.

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `worker_id` | `str` | Yes | Worker UUID |

**Returns:**
```json
{
  "worker_id": "...",
  "status": "working",
  "output_lines": "...",
  "updated_at": "...",
  "pending_relay": null
}
```

Or `{"error": "worker_not_found"}`.

`pending_relay` is non-null when a relay event is queued for the worker: `{"relay_id", "relay_type", "details"}`.

**Worker statuses:**
- `working` — agent is actively processing
- `waiting` — agent is idle at the prompt
- `ask_user` — agent is showing an AskUserQuestion prompt
- `check_permission` — agent is waiting for tool approval
- `done` — session ended

---

### `get_output`

Capture recent pane output from a worker's tmux session.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `worker_id` | `str` | Yes | — | Worker UUID |
| `scrollback` | `int` | No | `200` | Lines of scrollback to capture |

**Returns:** `{"worker_id": str, "lines": str}` or `{"error": "worker_not_found"}`

---

### `terminate_worker`

Terminate a worker and clean up its tmux session and database row.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `worker_id` | `str` | Yes | — | Worker UUID |
| `force` | `bool` | No | `false` | Reserved for future use |

**Returns:** `{"worker_id": str, "terminated": true}` or `{"error": "worker_not_found"}`

---

## Architecture

Waggle v2 has 7 components:

1. **HTTP Daemon** (`daemon.py`) — Uvicorn server binding to `127.0.0.1` on the configured port (default 8422). Initializes the database schema on startup.
2. **MCP Server** (`server.py`) — FastMCP instance mounted at `/mcp` inside a Starlette application. Thin tool adapters that extract caller identity from the MCP session context and delegate to the engine.
3. **Core Engine** (`engine.py`) — All business logic: spawn, terminate, status checks, output capture. Returns plain dicts with an `"error"` key on failure. No MCP or HTTP types in signatures.
4. **SQLite Database** — 4 tables: `workers`, `callers`, `requests`, `pending_relays`. WAL mode enabled for concurrent reads during hook writes.
5. **tmux Manager** (`tmux.py`) — Session creation, pane capture, and agent launch via libtmux. Sets `WAGGLE_WORKER_ID` in the tmux environment so hooks can identify the worker.
6. **State Parser** (`state_parser.py`) — Classifies raw pane content into agent states (working / waiting / ask_user / check_permission / done / unknown).
7. **CLI** (`cli.py`) — `waggle serve` starts the daemon. Hook commands: `waggle set-state [state]`, `waggle set-state --delete`, `waggle permission-request`, `waggle ask-relay`.

## Configuration

Create `~/.waggle/config.json` to override defaults. All keys are optional.

```json
{
  "database_path": "~/.waggle/state.db",
  "queue_path": "~/.waggle/queue.db",
  "max_workers": 8,
  "http_port": 8422,
  "mcp_worker_port": 8423,
  "repos_path": "~/.waggle/repos",
  "relay_timeout_seconds": 3600,
  "state_poll_interval_seconds": 2,
  "output_capture_lines": 50,
  "authorized_keys_path": "~/.waggle/authorized_keys.json",
  "admin_email": "",
  "admin_notify_after_retries": 5,
  "max_retry_hours": 72,
  "tls_cert_path": "",
  "tls_key_path": ""
}
```

| Key | Default | Description |
|-----|---------|-------------|
| `database_path` | `~/.waggle/state.db` | Path to the SQLite state database |
| `queue_path` | `~/.waggle/queue.db` | Path to the queue database |
| `max_workers` | `8` | Maximum concurrent workers (global) |
| `http_port` | `8422` | Port for the HTTP daemon |
| `mcp_worker_port` | `8423` | Port reserved for MCP worker connections |
| `repos_path` | `~/.waggle/repos` | Directory where remote repos are cloned |
| `relay_timeout_seconds` | `3600` | How long pending relays are retained |
| `state_poll_interval_seconds` | `2` | Polling interval for state updates |
| `output_capture_lines` | `50` | Default lines captured for output snapshots |
| `authorized_keys_path` | `~/.waggle/authorized_keys.json` | Authorized keys for remote access |
| `admin_email` | `""` | Email for admin notifications |
| `admin_notify_after_retries` | `5` | Retry count before notifying admin |
| `max_retry_hours` | `72` | Maximum hours to retry failed operations |
| `tls_cert_path` | `""` | TLS certificate path (future HTTPS support) |
| `tls_key_path` | `""` | TLS key path (future HTTPS support) |

## Troubleshooting

**Verify dependencies:**

```bash
which tmux sqlite3 python3
```

All commands must be found. Install missing dependencies via package manager.

**Verify database access:**

```bash
sqlite3 ~/.waggle/state.db "SELECT COUNT(*) FROM workers;"
```

Should return a count without error. If the file is locked, find what holds it:

```bash
lsof ~/.waggle/state.db
```

**Recover from corruption:**

```bash
rm ~/.waggle/state.db
```

The daemon recreates the schema on next startup.

**Check daemon is running:**

```bash
curl http://localhost:8422/mcp
```

If unreachable, start the daemon with `waggle serve`.

## Security

**WARNING: No access control implemented.**

- The HTTP daemon binds to `127.0.0.1` only (not accessible over the network by default)
- Database is unprotected (filesystem permissions only)
- Any local process can read/write worker state

**Suitable for single-user development environments only.**

Do not expose the waggle port externally or use waggle on shared systems with sensitive data.

## License

MIT License - see [LICENSE](LICENSE) file for details.
