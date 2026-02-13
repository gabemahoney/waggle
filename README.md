# Waggle

MCP server for tracking async agent state in tmux sessions.

## Overview

Waggle enables LLM orchestrators to monitor the state of any Claude and OpenCode LLM sessions running inside tmux. 
Uses hook-driven state updates to track whether agents are working or waiting for input.

## Installation

**Dependencies:**
- tmux
- sqlite3
- python3

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

### Basic Usage ###

The MCP server will advertise its capabilities. Just ask your LLM to "list sessions" or something similar.
For each active session it will show:
- tmux session name
- status (defined by you during configuration, above)
- directory of that agent
- tmux session id

### Advanced Usage ###

The server also offers the ability to forcibly delete entries from the db if for some reason it ever gets into a bad state.

**Architecture:**

Waggle has 4 components:

1. **MCP Server** - Provides `list_agents`, `delete_repo_agents` tools
2. **SQLite Database** - Persistent agent state tracking with session identity keys
3. **tmux Sessions** - Isolated environments for async agents
4. **State Tracking Integration** - Auto-update database on agent state changes
   - **Claude Code**: Bash hooks called on session lifecycle events
   - **OpenCode**: TypeScript plugin responds to session events


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
