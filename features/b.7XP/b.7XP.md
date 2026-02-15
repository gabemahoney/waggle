---
id: b.7XP
type: bee
title: Add libtmux-based MCP tools for agent interaction
labels:
- libtmux
- mcp-tools
- orchestration
status: open
created_at: '2026-02-15T12:47:10.908940'
updated_at: '2026-02-15T12:47:10.908942'
bees_version: '1.1'
priority: 1
---

## Problem Statements

Waggle can tell an orchestrator agent *what* agents exist and *what state* they're in, but provides no way to actually interact with them. 
An orchestrator that sees a `waiting` agent has no mechanism to give it work, read its output, or check what it's doing. 
The only option today is for a human to manually switch tmux sessions and type.

This makes multi-agent orchestration impossible through waggle alone. 
The orchestrator is blind and mute — it can see agents but can't talk to them or hear what they're saying.

Agents also need to spawn remote sessions via tmux primitives which is not robust.

### Current Limitations

- **No input channel**: No way to send text, commands, or keystrokes to an agent's tmux session
- **No output channel**: No way to read what's on an agent's screen (pane content, scrollback)
- **Fragile tmux layer**: Raw `subprocess.run(["tmux", ...])` with manual format string parsing — error-prone, hard to extend
- **Read-only interaction model**: `list_agents` and `delete_repo_agents` are the only tools — both are passive
- **Spawn Agent skill uses tmux cmd line**: Agents spawn other agents via tmux cmd line which is error prone

## Solution Requirements

### Must Have

1. **Send text to an agent's tmux pane** — an orchestrator can type commands, prompts, or keystrokes into a waggle-registered agent's session
2. **Read an agent's pane output** — an orchestrator can capture what's currently visible (with scrollback) from an agent's tmux pane
3. **Agent validation** — only allow interaction with agents registered in waggle's DB (security boundary — can't target arbitrary tmux sessions)
4. **Multi-pane support** - Claude Agent Teams sometimes forces multi-pane layout so solution must be capable of finding and communicating with main agent pane
5. **Support for spawning agents** - provide cmd for establishing tmux session and spawning an agent in it

### Won't Have (this iteration)

- Bidirectional streaming / real-time output watching

## Research required

- How can we support reading and writing to multi-pane sessions for main agent / subagent workflow?
  - Specifically Claude Agent Teams which uses the multipane layout
  - Can the main @team_lead agent be identified? This will be the only one we ever want to interact with
  - Can sub-agents be identified by name?
- Need to develop a test harness for building this to prove it out
  - Test harness must launch a tmux session with Claude
  - Harness must get it into states to be tested (Working, Done, AskUserQuestion and CheckPermission)
  - Harness can be used to check that `send_command` and `read_pane` work as expected for these states
    - Each state can be read correctly
    - The Done, AskUserQuestion and CheckPermission states can be responded to correctly
- Research https://github.com/tmux-python/libtmux
  - Determine what capabilities we can leverage to make this solution robust
  - Offer ideas for enhanced functionality not requested here that might help solve for the problem statement

## New MCP Tools

`send_command`
- **Note**: Pane targeting approach (multi-pane sessions) TBD per Research section
- State-aware: reads pane state before sending. Refuses to send if agent is in Working state (returns error: "agent is busy").
- ensures the text input field is clear
- sends a command along with return to complete it
- Verifies delivery: polls pane state after sending to confirm agent transitioned (e.g., from Done to Working). Timeout after 5s, returns error on failure. No automatic retry.
- Auto-formats responses for AskUserQuestion (sends number selection) and CheckPermission (sends 1/2) prompts
- For Done state: sends freeform text as-is
- `send_command` takes the following params:
  - session_id: tmux session id to send command to
  - command: the command to send as a string
- Returns: `{status: "success"|"error", message: str}`
`read_pane`
- **Note**: Pane targeting approach (multi-pane sessions) TBD per Research section
- reads current status of pane to determine agent state
- is capable of understanding the following states:
  - Working: the agent is working and generating tokens
  - Done: the agent has stopped outputting and is waiting for input in the input field
  - AskUserQuestion: The agent is using the LLM skill called AskUserQuestion which offers a multiple choice question UI
    - Is capable of relaying the Question text back to the calling LLM so that LLM can present it as an AskUserQuestion to the User
    - User can then answer that AskUserQuestion and waggle will use `send_command` to answer the downstream agent
  - CheckPermission: The agent is asking for permission to perform an action.
    - Is capable of relaying the permission check question back to the calling Agent so it can present it to the User to get an answer
- `read_pane` takes the following params:
  - session_id: tmux session id to read from
  - scrollback [optional, default: 50, no max]: number of scrollback lines to return.
- Returns: `{status: "success"|"error", agent_state: "working"|"done"|"ask_user"|"check_permission", content: str, prompt_data: dict|null}`
  - `prompt_data` populated when agent_state is `ask_user` or `check_permission` with structured question/options
`spawn_agent`
- `spawn_agent` takes the following params:
  - repo: the directory of the repo to spawn the agent in
  - session_name: the name of the tmux session to use
  - agent: claude or opencode
  - model [optional]: the claude model to use (Haiku, Sonnet or Opus)
  - command [optional]: the command to give the agent when it starts
  - settings [optional]: any command line params (e.g --dangerously-skip-permissions)
- Session resolution logic:
  - if session_name does not exist → create tmux session at repo path, launch LLM agent
  - if session_name exists AND is running an LLM instance → error: "LLM already running in session"
  - if session_name exists AND is NOT running an LLM instance:
    - if session is in the requested repo → launch LLM agent in existing session
    - if session is in a different repo → error: "session exists but is in wrong repo"
- Returns: `{status: "success"|"error", session_id: str, session_name: str, message: str}`
`close_session`
- `close_session` takes the following params:
  - `session_name` [optional]: tmux session name. can be provided to remove ambiguity
  - `session_id`: the tmux session_id to close
  - `force` [optional, default: false]: required when session has an active LLM agent
  - if both `session_name` and `session_id` are provided, `close_session` will only close the session if both match
- cleans up an active session
- if the session is running an LLM agent then it must be called with `-force` 
  - otherwise returns an error saying "Active LLM agent, call again with -force to confirm"
- otherwise, closes the tmux session
- Returns: `{status: "success"|"error", message: str}`

## Technical Requirements

- all existing tmux interaction (`list_agents`, `cleanup_dead_sessions`) to use libtmux for a single, consistent tmux interface. No backwards compatibility required — tool contracts can change.
- use libtmux for all new agent communication channels as well
- Async-safe — libtmux is synchronous; all calls must be wrapped with `asyncio.to_thread()` to avoid blocking the MCP event loop

## Info

Example AskUserQuestion text:
```
All 6 acceptance criteria verified. Are you ready to mark Epic features.bees-lpw as finished?

❯ 1. Yes, mark as finished
     All acceptance criteria met. Close the Epic.
  2. No, more work needed
     There's additional work before this Epic can be closed.
  3. Type something.
───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  4. Chat about this
```

Example CheckPermission text:
```
 Bash command

   git log --oneline -5
   Recent commits

 Permission rule Bash requires confirmation for this command.

 Do you want to proceed?
 ❯ 1. Yes
   2. No
```
