# close_session Architecture

## Overview

`close_session` is an MCP tool that terminates a waggle-managed tmux session and removes its corresponding database entry. It provides a controlled teardown path with safety checks: DB-existence validation, optional name disambiguation, and LLM-running protection (requiring explicit `force=true` to kill a session with an active agent).

Defined in `src/waggle/server.py`. Delegates tmux operations to `src/waggle/tmux.py`.

## Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `session_id` | `str` | Yes | — | tmux session ID (e.g. `"$1"`) |
| `session_name` | `str \| None` | No | `None` | Optional name to validate against — prevents closing the wrong session if IDs have been recycled |
| `force` | `bool` | No | `False` | If `True`, close even when an LLM agent is actively running |

## DB-First Cleanup Ordering

The DB entry is deleted **before** the tmux session is killed. This ordering is intentional:

- **DB is the source of truth** for waggle. Removing the entry first ensures `list_agents` and other DB-reading tools immediately stop reporting the session, even if the tmux kill takes time or fails.
- **Partial failure is safe.** If the DB delete succeeds but the tmux kill fails, the result is an orphaned tmux session with no waggle tracking — a benign state. The caller is informed and can use raw tmux commands to clean up.
- **Reverse ordering is worse.** If tmux were killed first and the DB delete failed, waggle would have a dangling DB entry pointing at a dead session — a state that confuses `list_agents` until `cleanup_dead_sessions` runs.

## LLM Protection

Prevents accidental termination of sessions with active LLM agents (SR-8).

**Detection method** (`tmux.py:is_llm_running`):
- Reads `pane_current_command` from the session's active pane via libtmux
- Returns `True` if the command is `claude` or `opencode` (case-insensitive)
- Single tmux query — no process tree walking, no pgrep/psutil (SR-8.1)
- Returns `False` on any error (fail-open for detection, fail-closed for protection)

**Async wrapper** (`tmux.py:check_llm_running`):
- Offloads the synchronous libtmux call to a thread via `asyncio.to_thread`
- Resolves session by ID, gets active window's active pane, calls `is_llm_running`

**Protection flow:**
- If LLM is running and `force=False`: return error prompting caller to retry with `force=True`
- If LLM is running and `force=True`: proceed with teardown
- If LLM is not running: proceed regardless of `force` value

## Error Conditions

| Condition | Step | Response |
|-----------|------|----------|
| DB query fails | 1 | `{status: "error", message: "Failed to query database: ..."}` |
| `session_id` not in DB | 1 | `{status: "error", message: "Session '$id' not found in database"}` |
| `session_name` doesn't match tmux | 2 | `{status: "error", message: "Session name mismatch: expected '...', found '...'"}` |
| LLM running, `force=false` | 4-5 | `{status: "error", message: "Active LLM agent, call again with force=true to confirm"}` |
| DB delete fails | 6 | `{status: "error", message: "Failed to delete database entry: ..."}` |
| tmux kill fails after DB delete | 7-8 | `{status: "error", message: "DB entry removed but tmux session kill failed: ..."}` |

## Return Contract

```
{"status": "success" | "error", "message": str}
```

On success: `{"status": "success", "message": "Session closed"}`

On error: `{"status": "error", "message": "<description>"}` — message varies by error condition (see table above).

## Sequence Diagram

```mermaid
sequenceDiagram
    participant C as Caller
    participant CS as close_session
    participant DB as SQLite DB
    participant TM as tmux.py
    participant TX as tmux/libtmux

    C->>CS: close_session(session_id, session_name?, force?)

    Note over CS: Step 1: Validate session_id in DB
    CS->>DB: SELECT key FROM state
    DB-->>CS: all_keys
    CS->>CS: Find key where parts[1] == session_id
    alt session_id not found
        CS-->>C: error "Session not found in database"
    end

    Note over CS: Step 2: Validate session_name (if provided)
    opt session_name provided
        CS->>TM: validate_session_name_id(session_id, session_name)
        TM->>TX: get session by ID, compare name
        TX-->>TM: match / mismatch
        TM-->>CS: success / error
        alt name mismatch
            CS-->>C: error "Session name mismatch"
        end
    end

    Note over CS: Step 3: Check LLM running
    CS->>TM: check_llm_running(session_id)
    TM->>TX: get session → active_window → active_pane
    TX-->>TM: pane_current_command
    TM->>TM: is_llm_running(pane)
    TM-->>CS: true / false

    Note over CS: Steps 4-5: Enforce force flag
    alt LLM running AND force=false
        CS-->>C: error "Active LLM agent, call again with force=true"
    end

    Note over CS: Step 6: DB-first delete
    CS->>DB: DELETE FROM state WHERE key = matching_key
    alt DB delete fails
        CS-->>C: error "Failed to delete database entry"
    end

    Note over CS: Step 7: Kill tmux session
    CS->>TM: kill_session(session_id)
    TM->>TX: server.sessions.get(session_id).kill()
    TX-->>TM: success / error

    Note over CS: Steps 8-9: Report result
    alt tmux kill failed
        CS-->>C: error "DB entry removed but tmux kill failed"
    else tmux kill succeeded
        CS-->>C: success "Session closed"
    end
```
