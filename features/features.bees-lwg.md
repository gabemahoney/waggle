---
id: features.bees-lwg
type: subtask
title: Implement refactoring of get_connection() based on analysis decision
up_dependencies:
- features.bees-mpi
down_dependencies:
- features.bees-vxi
- features.bees-nhn
- features.bees-c42
parent: features.bees-itu
created_at: '2026-02-12T11:48:18.655435'
updated_at: '2026-02-12T12:07:02.777190'
status: completed
bees_version: '1.1'
---

**Context:** Based on decision from previous subtask, implement the refactoring of get_connection() in src/waggle/database.py:48-64.

**Implementation options:**
- Option A: Inline get_connection() code directly into connection() context manager
- Option B: Rename get_connection() to _get_connection() to make it private

**What to do:**
1. Apply the chosen refactoring approach
2. Ensure connection() context manager still works correctly
3. Update any imports or references if needed

**Affected files:** src/waggle/database.py

**Acceptance:** 
- get_connection() is either inlined or renamed to _get_connection()
- connection() context manager functionality unchanged
- Code is cleaner and follows Python conventions
