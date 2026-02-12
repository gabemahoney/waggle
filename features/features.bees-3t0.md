---
id: features.bees-3t0
type: t2
title: Fix race condition in cleanup_all_agents
parent: features.bees-r2u
children:
- features.bees-1pa
- features.bees-plt
- features.bees-a3l
- features.bees-dup
- features.bees-wj2
created_at: '2026-02-11T22:27:23.143891'
updated_at: '2026-02-11T23:14:23.456357'
status: closed
bees_version: '1.1'
---

Fix the race condition in `cleanup_all_agents` function in `server.py:270-281`.

## Problem
Currently the function does a COUNT query followed by a DELETE query. Between these two queries, another process could modify the database, causing the returned count to be inaccurate.

## Solution
Use `cursor.rowcount` after the DELETE statement instead of a separate COUNT query. This provides the accurate count of rows actually deleted.

## Files to Modify
- `src/waggle/server.py` (lines 270-281)

## Acceptance Criteria
- `cleanup_all_agents` returns the count from `cursor.rowcount` after DELETE
- No separate COUNT query before DELETE
- Function still returns accurate deleted count
