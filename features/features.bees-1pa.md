---
id: features.bees-1pa
type: t3
title: Replace COUNT+DELETE with DELETE+rowcount in cleanup_all_agents
down_dependencies:
- features.bees-plt
- features.bees-a3l
- features.bees-dup
parent: features.bees-3t0
created_at: '2026-02-11T22:27:31.338201'
updated_at: '2026-02-11T23:13:08.411375'
status: closed
bees_version: '1.1'
---

Modify `cleanup_all_agents` in `src/waggle/server.py` to eliminate race condition:

1. Remove the COUNT query that runs before DELETE
2. Execute the DELETE statement
3. Use `cursor.rowcount` to get the number of deleted rows
4. Return this count in the response

This ensures the returned count matches exactly what was deleted.
