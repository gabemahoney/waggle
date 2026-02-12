---
id: features.bees-9rm
type: task
title: Remove composite_key alias in server.py
parent: features.bees-02t
children:
- features.bees-f1g
- features.bees-eod
created_at: '2026-02-12T11:47:15.863158'
updated_at: '2026-02-12T12:16:20.121301'
priority: 0
status: completed
bees_version: '1.1'
---

Context: Line 221 has a useless variable assignment `composite_key = key` that adds no value.

What Needs to Change:
- Replace all uses of composite_key with key in the loop starting at line 218
- Remove the `composite_key = key` assignment

Files: src/waggle/server.py

Bee: features.bees-02t

Success Criteria:
- composite_key variable is gone
- Code uses key directly
- All tests pass
