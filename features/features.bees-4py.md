---
id: features.bees-4py
type: subtask
title: Remove useless exception re-raise in server.py
parent: features.bees-1qh
created_at: '2026-02-11T22:26:55.100454'
updated_at: '2026-02-11T22:41:39.570158'
status: completed
bees_version: '1.1'
---

**Context**: `server.py:50-51` has `except Exception: raise` which does nothing useful.

**What to do**:
- Remove the `except Exception: raise` block in `src/waggle/server.py:50-51`
- Ensure the try block either has a meaningful except handler or is removed entirely

**Acceptance**: No useless exception re-raise pattern in server.py.
