# terminate_worker Architecture

## Overview

`terminate_worker` shuts down a waggle-managed worker: kills the tmux session and removes the worker row from the database.

Defined in `src/waggle/engine.py`. Delegates tmux operations to `src/waggle/tmux.py`.

## Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `caller_id` | `str` | Yes | — | Caller requesting termination (scope check) |
| `worker_id` | `str` | Yes | — | UUID of the worker to terminate |
| `force` | `bool` | No | `False` | Reserved for future active-worker protection |

## Flow

1. **DB lookup** — find worker by `worker_id`
2. **Caller scope check** — verify `caller_id` matches the worker's owner; return `worker_not_found` if not (no information leakage)
3. **Kill tmux session** via `kill_session(session_id)`
4. **Delete worker row** from `workers` table
5. **Return** `{worker_id, terminated: True}`

## Errors

| Error | Condition |
|-------|-----------|
| `worker_not_found` | `worker_id` not in DB, or `caller_id` doesn't match |

## Sequence Diagram

```mermaid
sequenceDiagram
    participant C as Caller
    participant E as engine.py
    participant DB as SQLite DB
    participant TM as tmux.py
    participant TX as tmux/libtmux

    C->>E: terminate_worker(caller_id, worker_id, force?)

    Note over E: Step 1-2: DB lookup + scope check
    E->>DB: SELECT session_id FROM workers WHERE worker_id = ? AND caller_id = ?
    alt not found
        E-->>C: {error: "worker_not_found"}
    end

    Note over E: Step 3: Kill tmux session
    E->>TM: kill_session(session_id)
    TM->>TX: session.kill()
    TX-->>TM: ok

    Note over E: Step 4: Delete DB row
    E->>DB: DELETE FROM workers WHERE worker_id = ?
    DB-->>E: ok

    E-->>C: {worker_id, terminated: true}
```
