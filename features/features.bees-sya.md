---
id: features.bees-sya
type: t1
title: Create libtmux wrapper module
labels:
- libtmux
down_dependencies:
- features.bees-mlj
- features.bees-tx3
parent: features.bees-rao
created_at: '2026-02-14T20:59:38.331140'
updated_at: '2026-02-14T20:59:50.631571'
status: open
bees_version: '1.1'
---

## Goal

Create `src/waggle/tmux.py` — a module that encapsulates all libtmux interaction behind clean functions. Keeps `server.py` focused on MCP tool logic. Single place to handle libtmux exceptions.

## Functions

- `get_server()` → `libtmux.Server` — connect to tmux, raise RuntimeError if not running
- `find_session(server, session_id)` → `libtmux.Session` — lookup by session_id (e.g. "$1"), raise ValueError if not found
- `get_active_pane(session)` → `libtmux.Pane` — get `session.active_window.active_pane` (agents use single-pane sessions)
- `list_sessions(server)` → `list[dict]` — return session_name, session_id, session_created, session_path for all sessions (replaces subprocess `tmux list-sessions -F`)
- `send_keys(pane, text, enter=True, literal=False)` → None — thin wrapper around `pane.send_keys()`
- `capture_pane(pane, start=None, end=None)` → `list[str]` — thin wrapper around `pane.capture_pane()`

## Includes

- Add `libtmux = "^0.53.0"` to `pyproject.toml`
- Create `tests/test_tmux.py` with unit tests mocking `libtmux.Server`
