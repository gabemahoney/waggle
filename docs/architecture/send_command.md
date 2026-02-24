# send_command Architecture

## Overview

`send_command` is an MCP tool that delivers a command or input to an agent's tmux pane. It is state-aware: it inspects the agent's current state before sending, validates that the input is appropriate for that state (e.g. a valid option number for `ask_user` prompts), then polls for a state transition to confirm the command was received.

Defined in `src/waggle/server.py`. Delegates tmux operations to `src/waggle/tmux.py`.

## Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `session_id` | `str` | Yes | — | tmux session ID (e.g. `"$1"`) |
| `command` | `str` | Yes | — | Command text or option number to send to the pane |
| `pane_id` | `str \| None` | No | `None` | Optional pane ID. If omitted, uses the session's active pane |
| `custom_text` | `str \| None` | No | `None` | Free-form text for the "Type something." option in `ask_user` prompts. When provided, `command` must be the option number of "Type something." — the option is selected without Enter, then `custom_text` is typed and submitted |

## State-Aware Delivery

Before sending, the tool reads and parses the current pane content to determine agent state. Different states impose different constraints:

| Agent State | Behavior |
|-------------|----------|
| `working` | Rejected — returns `"agent is busy"` |
| `unknown` | Rejected — returns `"agent state unknown, cannot safely send"` |
| `done` | Accepted — `command` sent as-is |
| `ask_user` | Accepted only if `command` is a valid option number from the prompt |
| `check_permission` | Accepted only if `command` is `"1"` (yes) or `"2"` (no) |

### ask_user Validation

When the pane is showing an `ask_user` prompt, `state_parser.parse()` returns a `prompt_data` dict with:
- `"question"` — the question text
- `"currently_selected"` — the option number currently highlighted by `❯` (or `None`)
- `"options"` — list of option dicts, each with `"number"`, `"label"`, `"description"`, and `"navigation_required"`

The tool validates `command` against the set of valid option numbers. Invalid values are rejected with a descriptive error listing the valid choices.

Options with `navigation_required: true` appear below the `───` separator in the Claude Code TUI (e.g. "Chat about this"). These cannot be selected by typing their number directly — the tool navigates to them using Down arrow keys (see Input Sequence below).

### check_permission Validation

Permission prompts accept only `"1"` (approve) or `"2"` (deny). Any other value is rejected.

## Input Sequence

For receptive states, the send sequence depends on agent state:

**`done` state:**
1. `clear_pane_input(session_id, pane_id)` — sends `Ctrl+C` to discard any partial input
2. `send_keys_to_pane(session_id, command, pane_id)` — sends the command followed by Enter

**`ask_user` state (standard option):**
1. `send_keys_to_pane(session_id, command, pane_id)` — sends the option number followed by Enter (no Ctrl+C — would dismiss the dialog)

**`ask_user` state (`navigation_required` option):**
Options below the `───` separator (e.g. "Chat about this") cannot be selected by typing their number. Instead:
1. Compute the number of Down arrow presses needed: `target_index - current_index` using the ordered options list and `currently_selected` from `prompt_data`
2. Send `Down` key (without Enter) for each step, with `asyncio.sleep(0.05)` between presses
3. Send Enter to confirm the selection

If `currently_selected` is `None`, defaults to the first option in the list.

**`ask_user` state (`custom_text`):**
1. `send_keys_to_pane(session_id, command, pane_id, enter=False)` — selects "Type something." option without Enter
2. `asyncio.sleep(0.3)` — brief pause for the text input field to appear
3. `send_keys_to_pane(session_id, custom_text, pane_id)` — sends the custom text followed by Enter

**`check_permission` state:**
1. `send_keys_to_pane(session_id, command, pane_id)` — sends "1" or "2" followed by Enter (no Ctrl+C — would dismiss the dialog)

## Delivery Verification

After sending, the tool polls the pane at 0.5-second intervals for up to 5 seconds (10 polls), waiting for the agent state to change from the initial state. A state transition indicates the command was received and processing began.

- **Success**: state changed → `{"status": "success", "message": "command delivered"}`
- **Timeout**: no transition in 5s → `{"status": "error", "message": "command delivery unconfirmed: agent did not transition within 5 seconds"}`
- **No retry**: the command is sent exactly once regardless of timeout

## tmux.py Send Functions

Two new functions were added to `src/waggle/tmux.py` to support this tool:

### `send_keys_to_pane(session_id, text, pane_id=None, enter=True)`

Sends text to a tmux pane. Async wrapper over `_send_keys_to_pane_sync`.

- Resolves pane via `_resolve_pane()` helper (active pane or specific pane ID)
- Calls `pane.send_keys(text, enter=enter)`
- Validates pane belongs to the given session when `pane_id` is specified
- Catches both `LibTmuxException` and generic `Exception`

### `clear_pane_input(session_id, pane_id=None)`

Sends `Ctrl+C` (without Enter) to discard partial input. Async wrapper over `_clear_pane_input_sync`.

- Same pane resolution logic as `send_keys_to_pane`
- Calls `pane.send_keys("C-c", enter=False)`

### `_resolve_pane(server, session_id, pane_id)`

Internal helper shared by both send functions. Returns `(pane, error_dict)`:

- If `pane_id` is `None`: resolves `session.active_window.active_pane`
- If `pane_id` is provided: resolves via `server.panes.get(pane_id=pane_id)` and validates `pane.session_id == session_id`
- Returns `(None, error_dict)` if validation fails; callers check and return the error dict early

## Error Conditions

| Condition | Step | Response |
|-----------|------|----------|
| DB query fails | 1 | `{status: "error", message: "Failed to query database: ..."}` |
| `session_id` not in DB | 1 | `{status: "error", message: "Session '$id' not found in database"}` |
| `capture_pane` fails | 2 | error dict propagated from `capture_pane` |
| Agent is working | 3 | `{status: "error", message: "agent is busy"}` |
| Agent state unknown | 4 | `{status: "error", message: "agent state unknown, cannot safely send"}` |
| Invalid option for `ask_user` | 5 | `{status: "error", message: "invalid option '...'; valid options are: ..."}` |
| Invalid value for `check_permission` | 6 | `{status: "error", message: "invalid option; must be '1' (yes) or '2' (no) for permission prompts"}` |
| `clear_pane_input` fails | 7 | error dict propagated |
| `send_keys_to_pane` fails | 7 | error dict propagated |
| No state transition in 5s | 8–9 | `{status: "error", message: "command delivery unconfirmed: agent did not transition within 5 seconds"}` |

## Sequence Diagram

```mermaid
sequenceDiagram
    participant C as Caller
    participant SC as send_command
    participant DB as SQLite DB
    participant SP as state_parser
    participant TM as tmux.py
    participant TX as tmux/libtmux

    C->>SC: send_command(session_id, command, pane_id?)

    Note over SC: Step 1: Validate session in DB
    SC->>DB: SELECT key FROM state WHERE key LIKE '%+{session_id}+%'
    DB-->>SC: matching_key / None
    alt not found
        SC-->>C: error "Session not found in database"
    end

    Note over SC: Step 2: Read current pane state
    SC->>TM: capture_pane(session_id, pane_id)
    TM->>TX: pane.capture_pane(start=-scrollback)
    TX-->>TM: lines
    TM-->>SC: {status, content}
    SC->>SP: parse(content)
    SP-->>SC: (agent_state, prompt_data)

    Note over SC: Steps 3–6: State-based validation
    alt agent_state == "working"
        SC-->>C: error "agent is busy"
    else agent_state == "unknown"
        SC-->>C: error "agent state unknown, cannot safely send"
    else agent_state == "ask_user"
        SC->>SC: validate command in prompt_data options
        alt invalid option
            SC-->>C: error "invalid option '...'"
        end
    else agent_state == "check_permission"
        SC->>SC: validate command in {"1", "2"}
        alt invalid value
            SC-->>C: error "invalid option; must be '1' or '2'"
        end
    end

    Note over SC: Step 7: Send (state-dependent)
    alt agent_state == "done"
        SC->>TM: clear_pane_input(session_id, pane_id)
        TM->>TX: pane.send_keys("C-c", enter=False)
        SC->>TM: send_keys_to_pane(session_id, command, pane_id)
        TM->>TX: pane.send_keys(command, enter=True)
    else agent_state == "ask_user" and custom_text provided
        SC->>TM: send_keys_to_pane(session_id, command, pane_id, enter=False)
        TM->>TX: pane.send_keys(command, enter=False)
        Note over SC,TM: asyncio.sleep(0.3)
        SC->>TM: send_keys_to_pane(session_id, custom_text, pane_id)
        TM->>TX: pane.send_keys(custom_text, enter=True)
    else agent_state == "ask_user" and navigation_required
        Note over SC,TM: Compute downs = target_idx - current_idx
        loop downs times
            SC->>TM: send_keys_to_pane(session_id, "Down", pane_id, enter=False)
            TM->>TX: pane.send_keys("Down", enter=False)
            Note over SC,TM: asyncio.sleep(0.05)
        end
        SC->>TM: send_keys_to_pane(session_id, "", pane_id, enter=True)
        TM->>TX: pane.send_keys("", enter=True)
    else agent_state == "ask_user" or "check_permission"
        SC->>TM: send_keys_to_pane(session_id, command, pane_id)
        TM->>TX: pane.send_keys(command, enter=True)
    end
    TX-->>TM: ok
    TM-->>SC: {status: "success"}

    Note over SC: Steps 8–9: Poll for state transition (10x @ 0.5s)
    loop up to 10 times
        SC->>TM: capture_pane(session_id, pane_id)
        TM-->>SC: {status, content}
        SC->>SP: parse(content)
        SP-->>SC: (new_state, _)
        alt new_state != agent_state
            SC-->>C: success "command delivered"
        end
    end

    Note over SC: Step 9: Timeout
    SC-->>C: error "command delivery unconfirmed: agent did not transition within 5 seconds"
```
