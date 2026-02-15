---
id: features.bees-tx3
type: t1
title: Refactor existing tools from subprocess to libtmux
labels:
- refactor
- libtmux
up_dependencies:
- features.bees-sya
parent: features.bees-rao
created_at: '2026-02-14T20:59:45.390671'
updated_at: '2026-02-14T20:59:50.629583'
status: open
bees_version: '1.1'
---

## Goal

Replace all raw `subprocess.run(["tmux", ...])` calls in `server.py` with the `waggle.tmux` module from Epic 1.

## cleanup_dead_sessions()

- Replace subprocess call with `tmux.get_server()` + `tmux.list_sessions()`
- Build `active_sessions` set from libtmux dicts instead of parsing tab-separated format strings
- Same DB logic (batch delete orphaned keys)

## list_agents() enrichment block

- Replace subprocess tmux call with `tmux.list_sessions()`
- Build lookup map from libtmux dicts instead of parsing tab-separated output

## Remove from server.py

- `import subprocess`
- `TMUX_FIELD_SEP`, `TMUX_FMT_WITH_PATH`, `TMUX_FMT_KEYS_ONLY` constants

## Update tests

- Replace `mock_tmux_subprocess` fixture — mock `waggle.tmux` functions instead of `subprocess.run`
- Update all tests in `TestListAgents` and `TestCleanupDeadSessions`
- Remove `SEP = TMUX_FIELD_SEP` helper
