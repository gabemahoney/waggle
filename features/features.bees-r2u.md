---
id: features.bees-r2u
type: t1
title: Fix Database Race Conditions and Error Handling
parent: features.bees-f8i
children:
- features.bees-3t0
- features.bees-9id
created_at: '2026-02-11T22:26:56.361540'
updated_at: '2026-02-11T23:36:28.103214'
priority: 0
status: completed
bees_version: '1.1'
---

Fix two database reliability issues: race condition in cleanup_all_agents and missing explicit rollback in connection context manager.

## Work Items

1. **Fix race condition in `cleanup_all_agents`** (`server.py:270-281`)
   - Use `cursor.rowcount` after DELETE instead of separate COUNT query
   - Eliminates race between COUNT and DELETE

2. **Add explicit rollback in `connection()` context manager** (`database.py:63-86`)
   - Call `conn.rollback()` on exception before close
   - Makes error handling explicit rather than relying on SQLite auto-rollback

## Success Criteria
- `cleanup_all_agents` returns accurate deleted count from `cursor.rowcount`
- Connection context manager explicitly rolls back on exception
- `poetry run pytest` passes
