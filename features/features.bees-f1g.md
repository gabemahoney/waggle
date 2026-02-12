---
id: features.bees-f1g
type: subtask
title: Replace composite_key with key in loop at line 218-222
down_dependencies:
- features.bees-eod
parent: features.bees-9rm
created_at: '2026-02-12T11:47:57.902754'
updated_at: '2026-02-12T12:03:52.058575'
status: completed
bees_version: '1.1'
---

Context: Line 221 has a useless variable assignment `composite_key = key` that adds no value.

Files: src/waggle/server.py

Changes needed:
- Line 221: Remove the `composite_key = key` assignment
- Line 222: Change `state_map[composite_key]` to `state_map[key]`

Acceptance:
- composite_key variable is gone from lines 218-222
- Code uses key directly
- Code compiles without errors
