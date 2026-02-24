# Waggle

MCP server for tracking and managing async agent state in tmux sessions.

## Overview

Waggle enables LLM orchestrators to monitor and control Claude and OpenCode LLM sessions running inside tmux.
Uses hook-driven state updates to track whether agents are working or waiting for input, and provides tools to spawn, interact with, and close sessions.

## Installation

**Dependencies:**
- tmux 3.2a+
- sqlite3
- python3
- libtmux (installed automatically via poetry)

**Install Waggle:**

```bash
git clone https://github.com/gabemahoney/waggle.git
cd waggle
poetry install
```

## Quick Start

**Install hook scripts (required for both Claude Code and OpenCode):**

```bash
mkdir -p ~/.waggle/hooks
cp hooks/set_state.sh ~/.waggle/hooks/
chmod +x ~/.waggle/hooks/*.sh
```

<details>
<summary><strong>Claude Code Setup</strong></summary>

**1. Configure MCP Server**

This will allow you to use the MCP server in Claude Code.

Add to `~/.claude.json`:
```json
{
  "mcpServers": {
    "waggle": {
      "type": "stdio",
      "command": "poetry",
      "args": ["run", "--directory", "/path/to/waggle", "waggle"]
    }
  }
}
```

**Note:** Replace `/path/to/waggle` with the absolute path to your waggle installation.

**2. Configure Claude Hooks**

This will allow your Claude Code sessions to register their state in the database.
**Note**: You can change the `waiting` and `working` params to any state string you like.

Add to `~/.claude/settings.json`:

```json
{
  "hooks": {
    "SessionStart": [
      { "hooks": [{ "type": "command", "command": "~/.waggle/hooks/set_state.sh waiting" }] }
    ],
    "UserPromptSubmit": [
      { "hooks": [{ "type": "command", "command": "~/.waggle/hooks/set_state.sh working" }] }
    ],
    "PreToolUse": [
      { "matcher": "AskUserQuestion", "hooks": [{ "type": "command", "command": "~/.waggle/hooks/set_state.sh waiting" }] },
      { "matcher": "^(?!AskUserQuestion$).*", "hooks": [{ "type": "command", "command": "~/.waggle/hooks/set_state.sh working" }] }
    ],
    "PostToolUse": [
      { "hooks": [{ "type": "command", "command": "~/.waggle/hooks/set_state.sh working" }] }
    ],
    "PermissionRequest": [
      { "matcher": "*", "hooks": [{ "type": "command", "command": "~/.waggle/hooks/set_state.sh waiting" }] }
    ],
    "Stop": [
      { "hooks": [{ "type": "command", "command": "~/.waggle/hooks/set_state.sh waiting" }] }
    ],
    "Notification": [
      { "matcher": "*", "hooks": [{ "type": "command", "command": "~/.waggle/hooks/set_state.sh waiting" }] }
    ],
    "SessionEnd": [
      { "hooks": [{ "type": "command", "command": "~/.waggle/hooks/set_state.sh --delete" }] }
    ]
  }
}
```

Restart Claude Code after modifying configuration.

**3. Verify Setup**

```bash
claude mcp list
```

</details>

<details>
<summary><strong>OpenCode Setup</strong></summary>

**1. Configure MCP Server**

This will allow you to use the MCP server in OpenCode.

Add to `~/.opencode/opencode.json`:
```json
{
  "mcp": {
    "waggle": {
      "type": "local",
      "command": ["poetry", "run", "--directory", "/path/to/waggle", "waggle"]
    }
  }
}
```

**2. Install State Tracker Plugin**

This will allow your OpenCode sessions to register their state in the database.
OpenCode uses a plugin-based approach for state tracking. Install the plugin to `~/.opencode/plugins`:

```bash
mkdir -p ~/.opencode/plugins
cp plugins/opencode/state-tracker.ts ~/.opencode/plugins/
```

The plugin is automatically loaded at startup - no additional configuration required.

**3. Configure State Strings**

The plugin tracks two states: **idle** (waiting for input) and **working** (processing).
You may optionally configure custom state strings via environment variables:

```bash
export OPENCODE_STATE_IDLE="waiting"
export OPENCODE_STATE_WORKING="working"
```

Add these to your shell profile (`~/.bashrc` or `~/.zshrc`) to persist across sessions.

**Default values:** If not configured, the plugin uses `idle="waiting"` and `working="working"`.

**4. Verify Setup**

```bash
opencode mcp list
```

</details>

## How To Use It

### Basic Usage

The MCP server will advertise its capabilities. Just ask your LLM to "list sessions" or something similar.
For each active session it will show:
- tmux session name
- status (defined by you during configuration, above)
- directory of that agent
- tmux session id

When an agents checks on another agent it will also provide the following more detailed states:
- waiting — idle at prompt
- working — actively running
- ask_user — showing an AskUserQuestion prompt
- check_permission — waiting for tool approval
- done — session ended
- unknown

### Advanced Usage

The server also offers the ability to forcibly delete entries from the db if for some reason it ever gets into a bad state.

## MCP Tools

### `list_agents`

List all active agents tracked in waggle's database.

**Returns:** Array of agent objects with `name`, `status`, `directory`, `session_id`, `namespace` fields.

**Example:**
```
"List all agents" → returns list of tracked sessions with their current state
```

---

### `spawn_agent`

Launch a Claude or OpenCode agent in a new or existing tmux session.

**Parameters:**
| Parameter | Required | Description |
|-----------|----------|-------------|
| `repo` | Yes | Absolute path to the repository directory |
| `session_name` | Yes | tmux session name to create or reuse |
| `agent` | Yes | `"claude"` or `"opencode"` |
| `model` | No | Model name (e.g. `"sonnet"`, `"haiku"`, `"opus"`) |
| `command` | No | Initial command to deliver after agent reaches ready state |
| `settings` | No | Extra CLI flags (e.g. `"--dangerously-skip-permissions"`) |

**Session resolution:**
- Session doesn't exist → create new session at `repo` path
- Session exists + LLM running → error: "LLM already running in session"
- Session exists + no LLM + same repo → reuse existing session
- Session exists + no LLM + different repo → error: "session exists but is in wrong repo"

**Returns:** `{status, session_id, session_name, message}`

**Examples:**
```
"Spawn a claude agent in /my/project as session 'worker-1'"
→ creates tmux session, launches claude, registers in DB

"Spawn claude sonnet in /my/project with initial command 'help me refactor auth.py'"
→ waits up to 60s for agent to reach ready state, then delivers the command
```

---

### `read_pane`

Read the current content and state of an agent's tmux pane.

**Parameters:**
| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `session_id` | Yes | — | tmux session ID (e.g. `"$1"`) |
| `pane_id` | No | active pane | Specific pane ID for multi-pane sessions |
| `scrollback` | No | `50` | Number of scrollback lines to capture |

**Agent states detected:**
- `working` — agent is actively generating output ("Esc to interrupt" visible)
- `done` — agent is idle, waiting for input (`>` prompt visible)
- `ask_user` — agent is showing a numbered-option prompt (AskUserQuestion)
- `check_permission` — agent is requesting permission for a tool call
- `unknown` — content doesn't match any known pattern

**Returns:** `{status, agent_state, content, prompt_data}`
- `prompt_data` is populated for `ask_user` and `check_permission` states:
  - **`ask_user`**: `{question, currently_selected, options}` — `currently_selected` is the option number highlighted by `❯` (or `null`). Each option has `{number, label, description, navigation_required}`. Options with `navigation_required: true` appear below the `───` separator (e.g. "Chat about this"); `send_command` handles navigation automatically.
  - **`check_permission`**: `{tool_type, command, description}`

**Examples:**
```
"Read the pane for session $2"
→ {status: "success", agent_state: "done", content: "...", prompt_data: null}

"Check if agent in session $3 is waiting for input"
→ use read_pane and inspect agent_state
```

---

### `send_command`

Send a command or response to an agent's tmux pane.

**Parameters:**
| Parameter | Required | Description |
|-----------|----------|-------------|
| `session_id` | Yes | tmux session ID (e.g. `"$1"`) |
| `command` | Yes | Text to send (freeform, or option number for prompts) |
| `pane_id` | No | Specific pane ID for multi-pane sessions |
| `custom_text` | No | Free-form text for the "Type something." option in ask_user prompts. When set, `command` must be the number of the "Type something." option |

**State-aware behavior:**
- `working` state → rejected with `"agent is busy"`
- `unknown` state → rejected with `"agent state unknown, cannot safely send"`
- `done` state → `command` sent as-is
- `ask_user` state → `command` must be a valid option number (e.g. `"1"`, `"2"`). Options below the `───` separator (like "Chat about this") are navigated to automatically via Down arrow keys — just pass the option number as usual.
- `check_permission` state → `command` must be `"1"` (yes) or `"2"` (no)

For `done` state, sends `Ctrl+C` first to clear any partial input, then sends the command + Enter. For `ask_user` and `check_permission` states, `Ctrl+C` is skipped to avoid dismissing the dialog.
Polls up to 5 seconds for a state transition to confirm delivery.

**Returns:** `{status, message}`

**Examples:**
```
"Send 'run the tests' to session $2 (agent must be in done state)"

"Agent in $3 is showing an AskUserQuestion prompt with options 1-3, send option '2'"
→ send_command(session_id="$3", command="2")

"Approve the permission request in session $4"
→ send_command(session_id="$4", command="1")

"Send a custom reply to an ask_user prompt's 'Type something.' option"
→ send_command(session_id="$2", command="3", custom_text="my custom reply")
```

---

### `close_session`

Terminate a waggle-managed tmux session and remove its DB entry.

**Parameters:**
| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `session_id` | Yes | — | tmux session ID (e.g. `"$1"`) |
| `session_name` | No | `None` | Name to validate (prevents closing wrong session if IDs recycled) |
| `force` | No | `false` | Required to close a session with an active LLM agent |

**LLM protection:** If an LLM is actively running and `force=false`, returns an error asking you to retry with `force=true`.

**Returns:** `{status, message}`

**Examples:**
```
"Close session $2"
→ removes DB entry and kills tmux session

"Force close session $3 even though claude is running"
→ close_session(session_id="$3", force=true)
```

---

### `delete_repo_agents`

Remove all waggle DB entries for a specific repository path. Use to clean up stale or corrupted state.

**Returns:** `{status, deleted_count}`

---

## Architecture

Waggle has 4 components:

1. **MCP Server** (`src/waggle/server.py`) — Provides 6 tools: `list_agents`, `spawn_agent`, `read_pane`, `send_command`, `close_session`, `delete_repo_agents`
2. **SQLite Database** — Persistent agent state tracking with session identity keys (`session_name+session_id+session_created`)
3. **tmux Sessions** (`src/waggle/tmux.py`) — libtmux wrappers for session management, agent launch, pane interaction
4. **State Tracking Integration** — Auto-update database on agent state changes
   - **Claude Code**: Bash hooks called on session lifecycle events
   - **OpenCode**: TypeScript plugin responds to session events

**State detection** (`src/waggle/state_parser.py`) — Parses raw pane content to classify agent state (working / done / ask_user / check_permission / unknown).

## Advanced Configuration

Create `~/.waggle/config.json` to customize settings:

```json
{
  "database_path": "~/.waggle/agent_state.db"
}
```

All settings are optional with these defaults:
- `database_path`: `"~/.waggle/agent_state.db"`

## Troubleshooting

**Verify dependencies:**

```bash
which tmux sqlite3 python3
```

All commands must be found. Install missing dependencies via package manager.

**Verify database access:**

```bash
sqlite3 ~/.waggle/agent_state.db "SELECT COUNT(*) FROM state;"
```

Should return count without error. If locked, kill processes holding lock:

```bash
lsof ~/.waggle/agent_state.db
```

**Recover from corruption:**

```bash
rm ~/.waggle/agent_state.db
```

Server recreates schema on next startup. Hooks recreate state using UPSERT on next activity.

## Security

**WARNING: No access control implemented.**

- Database is unprotected (filesystem permissions only)
- Any process can read/write agent state
- Session names and paths visible in database

**Suitable for single-user development environments only.**

Do not use waggle on shared systems or with sensitive data.

## License

MIT License - see [LICENSE](LICENSE) file for details.
