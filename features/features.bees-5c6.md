---
id: features.bees-5c6
type: t3
title: Add conn.rollback() in exception handler of connection() context manager
down_dependencies:
- features.bees-ee1
- features.bees-2ki
- features.bees-4bd
parent: features.bees-9id
created_at: '2026-02-11T22:27:34.024850'
updated_at: '2026-02-11T23:16:02.399546'
status: closed
bees_version: '1.1'
---

Modify `connection()` context manager in `src/waggle/database.py`:

1. In the exception handling block (where exceptions are caught)
2. Before calling `conn.close()`, add `conn.rollback()`
3. This explicitly reverts any uncommitted changes on error

Makes error handling semantics explicit rather than relying on implicit SQLite behavior.
