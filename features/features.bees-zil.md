---
id: features.bees-zil
type: t2
title: Add timeout to tmux subprocess in list_agents
parent: features.bees-dcu
children:
- features.bees-2s5
- features.bees-5pv
- features.bees-n0p
- features.bees-gab
- features.bees-83d
created_at: '2026-02-11T22:27:27.732769'
updated_at: '2026-02-11T23:19:05.204509'
status: completed
bees_version: '1.1'
---

Add `timeout=5` to the `subprocess.run()` call in `list_agents` function (`server.py:153-158`).

## Context
The `list_agents` function calls tmux via subprocess without a timeout, which could hang indefinitely if tmux becomes unresponsive.

## Requirements
- Add `timeout=5` parameter to `subprocess.run()` call
- Matches pattern already used in `cleanup_dead_sessions`

## Acceptance Criteria
- `subprocess.run()` includes `timeout=5`
- Function handles `subprocess.TimeoutExpired` appropriately
- `poetry run pytest` passes
