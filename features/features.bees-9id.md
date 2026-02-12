---
id: features.bees-9id
type: t2
title: Add explicit rollback in connection() context manager
parent: features.bees-r2u
children:
- features.bees-5c6
- features.bees-ee1
- features.bees-2ki
- features.bees-4bd
- features.bees-vrr
created_at: '2026-02-11T22:27:26.237874'
updated_at: '2026-02-11T23:16:55.725838'
status: closed
bees_version: '1.1'
---

Add explicit rollback handling in the `connection()` context manager in `database.py:63-86`.

## Problem
The context manager currently relies on SQLite's implicit auto-rollback behavior when an exception occurs. This is implicit and could lead to confusion about error handling semantics.

## Solution
Call `conn.rollback()` explicitly in the exception handler before closing the connection. This makes the error handling behavior explicit and documented.

## Files to Modify
- `src/waggle/database.py` (lines 63-86)

## Acceptance Criteria
- Exception handler calls `conn.rollback()` before `conn.close()`
- Error handling is now explicit rather than implicit
- Existing tests continue to pass
