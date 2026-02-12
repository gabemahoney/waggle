---
id: features.bees-itu
type: task
title: Refactor get_connection() in database.py
parent: features.bees-02t
children:
- features.bees-mpi
- features.bees-lwg
- features.bees-vxi
- features.bees-nhn
- features.bees-c42
- features.bees-pvn
created_at: '2026-02-12T11:47:18.319859'
updated_at: '2026-02-12T12:16:20.922459'
priority: 0
status: completed
bees_version: '1.1'
---

Context: get_connection() at lines 48-64 is only used by the connection() context manager. It wraps sqlite3.connect() with minimal added value.

What Needs to Change:
- Evaluate if get_connection() should be inlined into connection() or made private
- Either inline the function or rename to _get_connection()

Files: src/waggle/database.py

Bee: features.bees-02t

Success Criteria:
- get_connection() is either private or inlined
- connection() context manager still works correctly
- All tests pass
