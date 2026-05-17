# Claude Spawn

Stateless stdio MCP server for managing Claude Code worker agents in tmux sessions.

## Overview

Claude Spawn is a lightweight stdio MCP server. An orchestrator Claude adds Claude Spawn as an MCP server, then uses the six Claude Spawn tools to spawn, monitor, and control Claude Code worker agents running in tmux sessions.

Claude Spawn delegates all state storage to [Claude Status](https://github.com/anthropics/claude-status), which it reads via the `claude-status` consumer CLI. Claude Spawn itself holds no database and runs no background daemon.

## Prerequisites

- tmux 3.2a+
- Python 3.10+
- [`claude-status`](https://github.com/anthropics/claude-status) on PATH

## Installation

```bash
git clone https://github.com/gabemahoney/claude-spawn.git
cd claude-spawn
pip install .        # or: poetry install
claude-spawn install # wires Claude Status hooks into ~/.claude/settings.json
```

`claude-spawn install` verifies that `claude-status` is available and runs `claude-status install-hooks` with the required relay and AUQ mode settings. Restart Claude Code after install.

Verify everything is wired correctly:

```bash
claude-spawn sting
```

## Register Claude Spawn as an MCP server

```bash
claude mcp add --transport stdio claude-spawn claude-spawn mcp
```

Verify:

```bash
claude mcp list
```

## MCP Tools

### `spawn_worker`

Spawn a new Claude Code worker in a tmux session.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `template` | `str` | No | None | Reserved for template loading (Epic 3); accepted but not loaded |
| `model` | `str` | No | inherits Claude Code | Claude model name |
| `thinking` | `str` | No | inherits Claude Code | Effort level — one of `low`, `medium`, `high`, `xhigh` |
| `cwd` | `str` | **Yes** | — | Absolute local path (or `~/...`) to the working directory |
| `tmux_session_name` | `str` | No | `<folder>-<instance_id[:8]>` | tmux session name |
| `instance_id` | `str` | No | UUIDv4 | Worker identifier |
| `claude_home` | `str` | No | inherits Claude Code | Override `HOME` for the spawned Claude process |
| `claude_settings` | `str` | No | inherits Claude Code | Path to a Claude settings JSON file; must exist |
| `extra_env` | `dict[str, str]` | No | `{}` | Additional environment variables for the session |
| `claude_status_labels` | `dict[str, str]` | No | `{}` | Extra Claude Status labels (bare key, auto-uppercased and prefixed) |
| `claude_args` | `list[str]` | No | `[]` | Arguments appended verbatim to the `claude` invocation |
| `permissions` | `dict` | No | `{}` | `{"allow": [], "deny": [], "ask": []}` permissions overlay |

**Per-option fallback category (SR-1.3):**

| Category | Parameters |
|----------|------------|
| Required (no fallback) | `cwd` |
| Hardcoded by Claude Spawn | `tmux_session_name`, `instance_id`, `extra_env`, `claude_status_labels`, `claude_args`, `permissions` |
| Inherits Claude Code default | `model`, `thinking`, `claude_home`, `claude_settings` |

Returns: `{"instance_id": str, "tmux_session_name": str}`

#### `cwd` accepts local paths only

`cwd` must be an absolute local filesystem path, or a `~`-prefixed path that expands via `os.path.expanduser`. The directory must already exist.

- HTTPS and SSH URLs are rejected with `ErrCwdNotAPath`. Claude Spawn never clones from a remote URL — pre-clone the repository, then pass the absolute path.
- Relative paths (e.g. `./myrepo`) are rejected with `ErrCwdNotAPath` so the resolved directory is never ambiguous about which process's working directory it is relative to.
- A non-existent path is rejected with `ErrCwdNotFound`. Claude Spawn does not create the directory.

#### Claude Code settings stack

Claude Code merges settings from four layers, lowest to highest precedence:

1. Enterprise managed settings (e.g. `/etc/claude-code/managed-settings.json`)
2. User settings — `<HOME>/.claude/settings.json`
3. Project shared settings — `<cwd>/.claude/settings.json`
4. Project local settings — `<cwd>/.claude/settings.local.json`

The CLI `--settings <path>` overlay wins above all four layers. Claude Spawn options map to this stack as follows:

- `claude_home` — rewrites `HOME` for the worker process, redirecting layer 2 to a different config tree.
- `claude_settings` — supplies the path passed via `--settings`, the highest-precedence overlay.
- `permissions` — realized inside that overlay. When no `claude_settings` is supplied, Claude Spawn synthesizes a minimal overlay containing just the `permissions` block. When both `claude_settings` and `permissions` are supplied, Claude Spawn writes a composite temp file with first-class `permissions.allow`/`deny`/`ask` layered on top of the caller's file (those three keys win; other top-level keys pass through unchanged).

Passing `--dangerously-skip-permissions` via `claude_args` alongside a non-empty `permissions` map is not an error; Claude Code's CLI-level bypass wins at runtime over the synthesized permissions overlay (SR-9.4).

#### Readiness blocking

`spawn_worker` blocks until the spawned worker registers with Claude Status. Once the call returns successfully, the returned `tmux_session_name` is immediately usable with `send_input`, `get_output`, `answer_question`, and `terminate_worker`.

The default timeout is **15 seconds** (not configurable per-call or per-template in v1).

**Timeout and early-exit errors:**

- `ErrSpawnReadinessTimeout` — returned when 15 seconds elapse without the worker registering with Claude Status. The orphaned tmux session is automatically killed via `tmux kill-session`; no manual cleanup is needed.
- `ErrSpawnWorkerExitedEarly` — returned when the worker's tmux session exits before registering. The error description includes captured pane output (`tmux capture-pane`) to aid diagnostics.

#### Templates

Option resolution follows a three-step chain: per-call argument → template field → SR-1.3 default. A template is consulted only when `template=<name>` is passed explicitly; a bare `spawn_worker(cwd=…)` call with no `template=` argument never reads the templates directory.

**Storage layout.** Templates live at `~/.claude-spawn/templates/<name>.toml`; the filename stem is the template name.

**TOML schema.** The top-level table may contain any of the 11 SR-1.1 option names (every parameter except `template` itself). Scalars (`cwd`, `model`, `thinking`, `tmux_session_name`, `instance_id`, `claude_home`, `claude_settings`) are TOML strings. `claude_args` is a TOML array of strings. Map options (`extra_env`, `claude_status_labels`, `permissions`) are TOML tables. Unknown keys and the `template` key are rejected at load time.

**Worked example** (`~/.claude-spawn/templates/orchestrator.toml`):

```toml
cwd = "/home/horde/projects/waggle-project/waggle-main"
model = "sonnet"
thinking = "high"
claude_args = ["--verbose"]

[extra_env]
LOG_LEVEL = "debug"

[permissions]
allow = ["Bash(git *)"]
deny = ["Bash(rm -rf *)"]
```

**Merge rules:**

1. *Scalars and lists* — per-call value replaces the template value wholesale when the per-call argument is not `None`. Example: template sets `model = "sonnet"`; caller passes `model="opus"` → effective model is `"opus"`.
2. *Maps* (`extra_env`, `claude_status_labels`, `permissions`) — shallow union: template keys form the base; per-call entries are layered on top; per-call wins on any colliding top-level key. A per-call empty `{}` still enters the merge path, so template-only keys are preserved. Example: template `extra_env = {LOG_LEVEL = "info"}` plus per-call `extra_env={"TRACE": "1"}` → `{LOG_LEVEL: "info", TRACE: "1"}`.
3. *Permissions sub-keys* — because `permissions` is a map, each sub-key (`allow`, `deny`, `ask`) is an independent top-level key in the merge. Example: template `permissions = {allow = ["Bash(git *)"]}` plus per-call `permissions={"deny": ["Bash(rm -rf *)"]}` → effective `{allow: ["Bash(git *)"], deny: ["Bash(rm -rf *)"]}`.

**Errors:**

- `ErrTemplateNotFound` — no `.toml` file exists for the requested name in the templates directory.
- `ErrTemplateMalformed` — the file was found but failed schema validation (TOML parse error, unknown key, forbidden `template` key, wrong value type, or invalid `thinking` value).

---

### `list_spawned_workers`

List all Claude Spawn-managed workers visible via Claude Status.

Returns:
```json
{
  "ok": true,
  "workers": [
    {"instance_id": "...", "session_name": "spawn-abc12345"}
  ]
}
```

To read full worker details (status, pending requests, labels), use `claude-status workers` or `claude-status worker <instance_id>` directly.

---

### `send_input`

Send text to a worker's tmux pane without pressing Enter.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `session_name` | `str` | Yes | tmux session name |
| `text` | `str` | Yes | Text to deliver (no implicit Enter) |

Returns: `{"ok": true, "operation": "send_input"}`

---

### `get_output`

Capture recent pane output from a worker's tmux session.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `session_name` | `str` | Yes | — | tmux session name |
| `scrollback` | `int` | No | `50` | Lines to capture (1–1000) |

Returns: `{"ok": true, "content": str}`

---

### `terminate_worker`

Kill a worker's tmux session.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `session_name` | `str` | Yes | tmux session name |

Returns: `{"ok": true, "operation": "terminate_worker"}`

---

### `answer_question`

Answer a worker's pending `AskUserQuestion`. The question text must still be visible in the pane.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `question_id` | `int` | Yes | `request_id` from the pending ask_user_question |
| `answer` | `str` | Yes | Answer text to deliver |

Returns: `{"ok": true, "operation": "answer_question"}`

---

## Error shape

Every tool returns an `ok` boolean. On failure:

```json
{
  "ok": false,
  "operation": "spawn_worker",
  "err_name": "ErrTmuxNewSession",
  "err_description": "session already exists"
}
```

---

## State and permissions

Claude Spawn does not manage permissions or worker state directly. Use `claude-status` for that:

```bash
# Read worker state
claude-status worker <instance_id>

# Approve or deny a pending permission request
claude-status decide <instance_id> allow
claude-status decide <instance_id> deny
```

---

## Architecture

Claude Spawn is three thin layers:

1. **`mcp_stdio.py`** — FastMCP stdio server; wraps each tool with SR-7.1 error handling
2. **`spawn.py`** — tool implementations; the only subprocess calls are to `tmux` (via `_tmux` seam) and `claude-status` (via `claude_spawn.claude_status._run` seam)
3. **`claude_status.py`** — consumer CLI client for `claude-status workers/worker/capabilities`

No HTTP, no SQLite, no background threads.

## Migrating from the old HTTP daemon

See [docs/migration.md](docs/migration.md) for step-by-step instructions on moving from the daemon + SQLite installation to the new stdio MCP + Claude Status setup.

## License

MIT License — see [LICENSE](LICENSE) file for details.
