# SRD: libtmux-based MCP Tools for Agent Interaction

**PRD Reference:** `features/b.7XP/b.7XP.md`
**Research Reference:** `features/b.7XP/research-findings.md`

---

## SR-1: Dependencies and Infrastructure

### SR-1.1: libtmux Dependency
- `libtmux` must be added as a runtime dependency in `pyproject.toml` under `[tool.poetry.dependencies]`, pinned to a minor version range (pre-1.0 library with potential breaking changes)
- Minimum tmux version 3.2a must be documented as a system requirement

### SR-1.2: Async Safety
- All libtmux calls are synchronous. Every libtmux interaction must be non-blocking to the MCP event loop
- Multiple sequential libtmux operations within a single tool call must be bundled into one synchronous function and offloaded as a single unit, not individually

### SR-1.3: Module Organization
- A new module must be created in `src/waggle/` for tmux interaction via libtmux, separate from `server.py`
- A new module must be created in `src/waggle/` for pane content state detection (parsing logic), separate from both the tmux module and `server.py`
- MCP tool definitions remain in `server.py`, delegating to the new modules

---

## SR-2: Existing Tool Migration

### SR-2.1: list_agents Refactor
- `list_agents` must use libtmux instead of `subprocess.run(["tmux", "list-sessions", ...])` for session enumeration
- The `TMUX_FMT_WITH_PATH`, `TMUX_FMT_KEYS_ONLY`, and `TMUX_FIELD_SEP` constants in `server.py` must be removed after migration — no raw tmux format string parsing should remain
- `list_agents` return contract may change — no backwards compatibility required per PRD

### SR-2.2: cleanup_dead_sessions Refactor
- `cleanup_dead_sessions` must use libtmux instead of `subprocess.run(["tmux", "list-sessions", ...])` to enumerate active sessions
- Orphan detection logic (DB keys not found in active tmux sessions) must be preserved
- Batch deletion behavior must be preserved

### SR-2.3: No Raw subprocess tmux Calls
- After migration, zero `subprocess.run(["tmux", ...])` calls may remain in `server.py` or any waggle module
- All tmux interaction must go through libtmux

---

## SR-3: State Detection

### SR-3.1: State Parser
- A dedicated parser must classify raw pane text content into one of five states: `working`, `done`, `ask_user`, `check_permission`, `unknown`
- The parser must operate on plain strings only — no tmux dependency, no I/O
- `unknown` must be returned when content does not match any known pattern (crashed agent, no agent, unexpected output)

### SR-3.2: Working State Detection
- Must detect the "Esc to interrupt" indicator present when an agent is actively generating output

### SR-3.3: Done State Detection
- Must detect the empty input prompt (`>`) indicating the agent is idle and waiting for user input
- Must not false-positive on `>` characters appearing in agent output text (only match the prompt at the bottom of the pane)

### SR-3.4: AskUserQuestion State Detection
- Must detect the numbered-option UI with `❯` selector character and horizontal rule separator (`───`)
- Must extract structured prompt data: question text and list of options (label + description for each)
- Must not false-positive on numbered lists in agent output text — the `❯` selector and separator line are the distinguishing signals

### SR-3.5: CheckPermission State Detection
- Must detect the "Do you want to proceed?" text combined with "Permission rule" text
- Must extract structured prompt data: tool type, command text, and description

### SR-3.6: State Priority
- When multiple patterns could match (e.g., a permission prompt contains numbered options), the parser must use a defined priority order to return the most specific state

---

## SR-4: read_pane Tool

### SR-4.1: Parameters
- `session_id` (required): tmux session ID to read from
- `pane_id` (optional): tmux pane ID for targeting a specific pane in multi-pane sessions. When omitted, reads the active pane of the session's active window
- `scrollback` (optional, default 50, no waggle-imposed maximum): number of scrollback lines to capture. Actual content is capped by tmux's `history-limit` setting. If fewer lines exist than requested, return what is available without error.

### SR-4.2: Validation
- Must validate `session_id` against waggle's DB. Return error if session is not registered
- If `pane_id` is provided, must validate the pane exists within the specified session

### SR-4.3: Return Contract
- Must return: `{status, agent_state, content, prompt_data}`
- `agent_state` must be one of: `working`, `done`, `ask_user`, `check_permission`, `unknown`
- `content` must contain the raw pane text (always populated, even for `unknown` state)
- `prompt_data` must be populated with structured question/options when `agent_state` is `ask_user` or `check_permission`, and `null` otherwise

---

## SR-5: send_command Tool

### SR-5.1: Parameters
- `session_id` (required): tmux session ID to send to
- `command` (required): text to send as a string
- `pane_id` (optional): tmux pane ID for targeting a specific pane in multi-pane sessions

### SR-5.2: Validation
- Must validate `session_id` against waggle's DB. Return error if session is not registered
- Must read pane state before sending. Must refuse to send if agent is in `working` state (return error: "agent is busy")
- Must refuse to send if agent is in `unknown` state (return error: "agent state unknown, cannot safely send")

### SR-5.3: Input Field Clearing
- Must send `Ctrl+C` to clear any partial input before sending content
- Must send the command text followed by a return/enter keystroke to submit it

### SR-5.4: Delivery Verification
- After sending, must poll pane state to confirm the agent transitioned (e.g., from `done` to `working`)
- Must timeout after 5 seconds if no transition is detected, returning an error
- Must not automatically retry on failure

### SR-5.5: State-Aware Formatting
- For `done` state: send freeform text as-is
- For `ask_user` state: caller sends the option number as a string (e.g., `"1"`, `"2"`). `send_command` validates it is a valid option number for the current prompt using `prompt_data` from state detection, then sends the keystroke
- For `check_permission` state: caller sends `"1"` (Yes) or `"2"` (No). `send_command` validates and sends the keystroke
- `read_pane`'s `prompt_data` provides structured options (number, label, description) so the caller can map labels to option numbers

### SR-5.6: Return Contract
- Must return: `{status, message}`

---

## SR-6: spawn_agent Tool

### SR-6.1: Parameters
- `repo` (required): directory path of the repo to spawn the agent in
- `session_name` (required): tmux session name to use
- `agent` (required): `claude` or `opencode`
- `model` (optional): Claude model to use (Haiku, Sonnet, or Opus)
- `command` (optional): command to deliver after agent reaches ready state
- `settings` (optional): additional CLI parameters (e.g., `--dangerously-skip-permissions`)

### SR-6.2: Session Resolution Logic
- If `session_name` does not exist as a tmux session: create a new session at the `repo` path, then launch the LLM agent
- If `session_name` exists AND the pane is running an LLM (per SR-8): return error "LLM already running in session"
- If `session_name` exists AND the pane is NOT running an LLM:
  - If the session's working directory matches `repo`: launch the LLM agent in the existing session
  - If the session's working directory does not match `repo`: return error "session exists but is in wrong repo"

### SR-6.3: Command Delivery Behavior
- Without `command`: return immediately after launching. Agent may still be initializing
- With `command`: after launching, poll with `read_pane` until agent reaches `done` state, then deliver `command` via `send_command`. Return after command is delivered
- Readiness polling must timeout after 60 seconds. On timeout, return error with last known agent state so the caller can decide next steps

### SR-6.5: DB Registration
- `spawn_agent` must register the new agent in waggle's DB immediately after session creation, before returning
- Registration must include: session_id, session_name, repo path, and agent type
- If the agent fails to start after registration, the stale entry will be cleaned up by `cleanup_dead_sessions`

### SR-6.4: Return Contract
- Must return: `{status, session_id, session_name, message}`

---

## SR-7: close_session Tool

### SR-7.1: Parameters
- `session_id` (required): tmux session ID to close
- `session_name` (optional): tmux session name, for disambiguation
- `force` (optional, default false): required when session has an active LLM agent

### SR-7.2: Validation
- Must validate `session_id` against waggle's DB. Return error if session is not registered
- If both `session_name` and `session_id` are provided, must verify they refer to the same session. Return error if they don't match

### SR-7.3: LLM Protection
- Must check whether the session pane is running an LLM (per SR-8)
- If an LLM is running and `force` is false: return error "Active LLM agent, call again with force=true to confirm"
- If an LLM is running and `force` is true: proceed with session kill

### SR-7.4: Cleanup
- Must remove the agent's DB entry first, then kill the tmux session (DB-first ordering)
- If tmux kill fails after DB removal, return error indicating DB was cleaned but session may still be alive
- Caller can use raw tmux commands to investigate the orphan session

### SR-7.5: Return Contract
- Must return: `{status, message}`

---

## SR-8: LLM Detection

### SR-8.1: Detection Method
- LLM presence in a pane must be determined by checking `pane_current_command` via libtmux
- A pane is considered to be running an LLM if `pane_current_command` equals `claude` or `opencode` (case-insensitive)
- No process tree walking, no `pgrep`/`psutil` — single tmux query only

### SR-8.2: Usage Points
- LLM detection must be used by `spawn_agent` (session resolution logic) and `close_session` (force protection)
- The detection logic must be a shared utility, not duplicated across tools

---

## SR-9: Multi-Pane Support

### SR-9.1: Pane Targeting
- `read_pane` and `send_command` must accept an optional `pane_id` parameter (tmux pane ID, e.g., `%5`)
- When `pane_id` is omitted, tools must target the active pane of the session's active window
- When `pane_id` is provided, tools must target that specific pane regardless of which pane is active

### SR-9.2: Pane Validation
- If a `pane_id` is provided, it must be validated to exist within the specified session
- Return a descriptive error if the pane does not exist or does not belong to the session

### SR-9.3: Team Lead DB Gating
- The Claude Code hook (`set_state.sh`) must check the `CLAUDE_CODE_AGENT_TYPE` environment variable before updating waggle's DB
- Only update the DB if the variable is unset (solo agent) or equals `"team-lead"`
- If set to any other value (teammate), skip the DB write silently
- This ensures only the team lead's state is tracked at session level for Agent Teams sessions

---

## SR-10: Error Handling

### SR-10.1: libtmux Exceptions
- All libtmux exceptions must be caught and converted to structured error responses (`{status: "error", message: ...}`)
- Tools must never propagate raw libtmux or tmux exceptions to the MCP client
- Both `LibTmuxException` subclasses and generic exceptions from `QueryList.get()` must be handled (known libtmux issue where some exceptions don't inherit from the base)

### SR-10.2: tmux Unavailability
- If tmux is not running or not installed, all tools must return a clear error message, not crash
- This must match the existing graceful-failure pattern in `cleanup_dead_sessions`

---

## SR-11: Test Fixtures and Testing

### SR-11.1: Test Architecture
- Tests live in `tests/`. Existing test files: `test_config.py`, `test_database.py`, `test_hooks.py`, `test_server.py`, `test_schema_conformance.py`, `test_concurrent.py`, `test_opencode_integration.py`
- Framework: pytest with pytest-asyncio. Mocking via `unittest.mock` (patch, MagicMock, AsyncMock)

### SR-11.2: Pane Content Fixtures
- Pre-recorded pane content snapshots must be captured from real Claude Code sessions for all 4 states: Working, Done, AskUserQuestion, CheckPermission
- Snapshots must be stored as text files under `tests/fixtures/pane_snapshots/` (one file per state)
- Snapshots must represent realistic pane output including any whitespace, prompt characters, and formatting

### SR-11.3: State Parser Tests
- A new test file must be created for state detection parser tests
- Tests must cover: correct classification of each state, extraction of `prompt_data` fields for `ask_user` and `check_permission`, `unknown` fallback for unrecognized content, no false positives (numbered lists in output not confused with `ask_user`, `>` in output not confused with `done` prompt)
- All parser tests must use the snapshot fixtures from SR-11.2 — no inline string literals for pane content

### SR-11.4: MCP Tool Tests
- New tool tests for `read_pane`, `send_command`, `spawn_agent`, and `close_session` must follow the existing pattern in `test_server.py`: mock the tmux layer, test validation logic, test return contracts
- Existing fixtures must be used: `mock_ctx` for FastMCP context, `temp_db`/`config_dir`/`temp_home` for database and config isolation
- libtmux must be mocked in tool tests — tool tests must not require a running tmux server

### SR-11.5: Migration Tests
- Tests for the refactored `list_agents` and `cleanup_dead_sessions` must be updated to mock libtmux instead of `subprocess.run`
- Behavioral assertions (orphan cleanup, filtering, enrichment) must be preserved — only the mocking layer changes

### SR-11.6: Schema Conformance
- If the DB schema changes (e.g., to support pane-level tracking), `test_schema_conformance.py` must be updated to verify the new schema matches between `schema.sql` and `hooks/set_state.sh`

---

## SR-12: Documentation

### SR-12.1: README Updates
- `README.md` must document the 4 new MCP tools (`read_pane`, `send_command`, `spawn_agent`, `close_session`) with parameter descriptions and example usage
- The libtmux system requirement (tmux 3.2a+) must be documented
- The `libtmux` Python dependency must be noted in installation instructions

### SR-12.2: Research Documentation
- Research findings must remain in `features/b.7XP/research-findings.md` as a record of design decisions

---

## SR-13: Future Considerations (Non-Requirements)

These items are documented for architectural awareness. They are NOT requirements for this iteration.

- **MCP Resource Subscriptions**: The MCP protocol supports server-initiated `notifications/resources/updated` messages. In theory, waggle could expose agent state as MCP resources and push state-change notifications to subscribed clients. In practice, these notifications are **cache invalidation signals** — the host application receives them, but there is no reliable mechanism for the host to interrupt or inject context into an LLM mid-turn. The LLM would only see updated data if it was already polling the resource. This means push notifications do not fundamentally change the orchestration pattern — explicit polling via `read_pane` remains the reliable approach. Revisit if MCP hosts gain support for injecting notifications between LLM turns.
- **Agent Teams Config Discovery**: A future iteration could read `~/.claude/teams/*/config.json` to automatically discover team structure and map pane IDs to named agents (team lead, sub-agents), enabling richer orchestration of multi-pane sessions.

---

## Acceptance Criteria Traceability

| PRD AC | Covered By |
|--------|-----------|
| 1. Four MCP tools implemented and functional | SR-4, SR-5, SR-6, SR-7 |
| 2. read_pane identifies all 4 agent states | SR-3, SR-4.3 |
| 3. send_command responds to AskUserQuestion and CheckPermission | SR-5.5 |
| 4. spawn_agent launches agent and delivers initial command | SR-6.3 |
| 5. Existing tmux interaction refactored to libtmux | SR-2 |
| 6. Research questions resolved with documented findings | SR-12.2 (complete) |
| 7. Test harness validates state detection and command delivery | SR-11.2, SR-11.3, SR-11.4 |
