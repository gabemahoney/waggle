# spawn_worker Architecture

## Overview

`spawn_worker` creates a new worker for a caller: checks concurrency limits, clones the repo if needed, creates a tmux session, launches claude, and records the worker in the database.

Defined in `src/waggle/engine.py`. Delegates tmux operations to `src/waggle/tmux.py`.

## Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `caller_id` | `str` | Yes | — | Caller performing the spawn |
| `model` | `str` | Yes | — | Claude model name (e.g. `"sonnet"`, `"haiku"`, `"opus"`) |
| `repo` | `str` | Yes | — | Local path or GitHub HTTPS URL |
| `session_name` | `str \| None` | No | `None` | tmux session name; generated as `waggle-{worker_id[:8]}` if omitted |
| `command` | `str \| None` | No | `None` | Initial command (reserved — Epic 3 adds delivery) |

## Flow

1. **Concurrency check** — count active workers (`status != 'done'`); reject if `>= max_workers`
2. **Generate UUID** for `worker_id`
3. **Generate session name** if not provided: `waggle-{worker_id[:8]}`
4. **Clone/pull repo** if URL via `clone_or_update_repo()`
5. **Create tmux session** via `create_session(session_name, local_repo, worker_id)` — sets `WAGGLE_WORKER_ID` env var
6. **Launch claude** via `launch_agent_in_pane(session_id, model)` — runs `claude --model {model}`
7. **Insert into workers table** (`status = 'working'`)
8. **Return** `{worker_id, session_name}`

## Claude Launch Command

`launch_agent_in_pane` sends the following command to the tmux pane:

```
claude --model {model}
```

Workers are plain Claude Code sessions with no additional flags. Input delivery is handled via `tmux send-keys` (see `send_input.md`).

## Errors

| Error | Condition |
|-------|-----------|
| `concurrency_limit_reached` | Active worker count >= max_workers |
| `repo_clone_failed` | git clone or fetch/reset failed |
| `invalid_repo` | URL cannot be parsed (no owner/repo path components) |

## Termination

`terminate_worker` (also in `engine.py`) performs cleanup after killing the tmux session:

1. **DB lookup + caller scope check** — find worker by `worker_id`; return `worker_not_found` if not present or caller doesn't own it
2. **Kill tmux session** — `kill_session(session_id)` removes the tmux session
3. **Delete worker row** — removes the row from the `workers` table

## Sequence Diagram

```mermaid
sequenceDiagram
    participant C as Caller
    participant E as engine.py
    participant TM as tmux.py
    participant TX as tmux/libtmux
    participant DB as SQLite DB

    C->>E: spawn_worker(caller_id, model, repo, session_name?, command?)

    Note over E: Step 1: Concurrency check
    E->>DB: SELECT COUNT(*) FROM workers WHERE status != 'done'
    alt count >= max_workers
        E-->>C: {error: "concurrency_limit_reached"}
    end

    Note over E: Steps 2-3: Generate IDs
    E->>E: worker_id = uuid4()
    E->>E: session_name = session_name or "waggle-{worker_id[:8]}"

    Note over E: Step 4: Clone/pull repo
    E->>TM: clone_or_update_repo_async(repo, repos_path)
    alt clone/fetch fails
        E-->>C: {error: "repo_clone_failed: ..."}
    end

    Note over E: Step 5: Create tmux session
    E->>TM: create_session(session_name, local_repo, worker_id)
    TM->>TX: server.new_session(...)
    TM->>TX: session.set_environment("WAGGLE_WORKER_ID", worker_id)
    TX-->>TM: new session
    TM-->>E: {status: "success", session_id, ...}

    Note over E: Step 6: Launch claude
    E->>TM: launch_agent_in_pane(session_id, model)
    TM->>TX: pane.send_keys("claude --model {model}", enter=True)
    TX-->>TM: ok
    TM-->>E: {status: "success"}

    Note over E: Step 7: DB insert
    E->>DB: INSERT INTO workers (worker_id, caller_id, session_name, session_id, model, repo, status='working')
    DB-->>E: ok

    E-->>C: {worker_id, session_name}
```
