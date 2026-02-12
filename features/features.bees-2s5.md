---
id: features.bees-2s5
type: t3
title: Add timeout=5 to subprocess.run() in list_agents
down_dependencies:
- features.bees-5pv
- features.bees-n0p
- features.bees-gab
parent: features.bees-zil
created_at: '2026-02-11T22:27:38.269017'
updated_at: '2026-02-11T23:18:14.853901'
status: completed
bees_version: '1.1'
---

In `server.py:153-158`, add `timeout=5` parameter to the `subprocess.run()` call for tmux.

## Files
- `src/waggle/server.py` lines 153-158

## Implementation
1. Locate the `subprocess.run()` call in `list_agents`
2. Add `timeout=5` to match the pattern in `cleanup_dead_sessions`
3. Handle `subprocess.TimeoutExpired` exception if not already handled

## Acceptance
- `subprocess.run()` includes `timeout=5`
