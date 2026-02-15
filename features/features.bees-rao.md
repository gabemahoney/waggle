---
id: features.bees-rao
type: bee
title: Add libtmux-based MCP tools for agent interaction
labels:
- libtmux
- mcp-tools
- orchestration
children:
- features.bees-sya
- features.bees-mlj
- features.bees-tx3
created_at: '2026-02-14T20:59:12.786998'
updated_at: '2026-02-14T21:02:29.466437'
priority: 1
status: open
bees_version: '1.1'
---

## Problem

Waggle can tell an orchestrator agent *what* agents exist and *what state* they're in, but provides no way to actually interact with them. An orchestrator that sees a `waiting` agent has no mechanism to give it work, read its output, or check what it's doing. The only option today is for a human to manually switch tmux sessions and type.

This makes multi-agent orchestration impossible through waggle alone. The orchestrator is blind and mute — it can see agents but can't talk to them or hear what they're saying.

### Current Limitations

- **No input channel**: No way to send text, commands, or keystrokes to an agent's tmux session
- **No output channel**: No way to read what's on an agent's screen (pane content, scrollback)
- **Fragile tmux layer**: Raw `subprocess.run(["tmux", ...])` with manual format string parsing — error-prone, hard to extend
- **Read-only interaction model**: `list_agents` and `delete_repo_agents` are the only tools — both are passive

## Solution Requirements

### Must Have

1. **Send text to an agent's tmux pane** — an orchestrator can type commands, prompts, or keystrokes into a waggle-registered agent's session
2. **Read an agent's pane output** — an orchestrator can capture what's currently visible (and optionally scrollback) from an agent's tmux pane
3. **Agent validation** — only allow interaction with agents registered in waggle's DB (security boundary — can't target arbitrary tmux sessions)
4. **Agent lookup by name** — tools accept the agent name as shown by `list_agents`, with optional `session_id` for disambiguation when names collide

### Should Have

5. **Replace subprocess with libtmux** — refactor all existing tmux interaction (`list_agents`, `cleanup_dead_sessions`) to use libtmux for a single, consistent tmux interface
6. **Async-safe** — libtmux is synchronous; all calls must be wrapped with `asyncio.to_thread()` to avoid blocking the MCP event loop

### Won't Have (this iteration)

- Agent spawning (already handled externally via spawn-agent skill)
- Bidirectional streaming / real-time output watching
- Multi-pane or multi-window support (agents use single-pane sessions)

## New MCP Tools

| Tool | Purpose | Key Params |
|------|---------|------------|
| `send_keys` | Send text/keystrokes to an agent's pane | `name`, `text`, `enter`, `session_id` |
| `read_pane` | Capture pane content from an agent | `name`, `start`, `end`, `session_id` |

## Architecture

- New module `src/waggle/tmux.py` encapsulates all libtmux calls
- `server.py` gets a `resolve_agent_pane()` helper that validates DB registration before resolving to a libtmux Pane object
- Existing subprocess tmux code in `list_agents` and `cleanup_dead_sessions` replaced with tmux module calls

## Files

| File | Action |
|------|--------|
| `src/waggle/tmux.py` | Create — libtmux wrapper module |
| `src/waggle/server.py` | Edit — add 2 tools + resolve helper, refactor existing |
| `tests/test_tmux.py` | Create — unit tests for tmux module |
| `tests/test_server.py` | Edit — update mocks, add tests for new tools |
| `pyproject.toml` | Edit — add libtmux dependency |
