---
id: features.bees-mpi
type: subtask
title: Analyze and decide whether to inline or make get_connection() private
down_dependencies:
- features.bees-lwg
parent: features.bees-itu
created_at: '2026-02-12T11:48:11.880372'
updated_at: '2026-02-12T12:06:49.837998'
status: completed
bees_version: '1.1'
---

**Context:** get_connection() at src/waggle/database.py:48-64 is only used internally by the connection() context manager at line 68. It wraps sqlite3.connect() with minimal added value.

**What to do:**
1. Review get_connection() implementation and its only caller connection()
2. Determine if inlining is better (simpler, fewer lines) or making it private (_get_connection) is better (separation of concerns)
3. Consider: error handling benefit, testability, readability

**Decision criteria:**
- If error handling adds no meaningful value → inline
- If keeping separation is cleaner → make private with _get_connection

**Affected files:** src/waggle/database.py

**Acceptance:** Decision documented in this ticket's description for next subtask to implement

---

**DECISION: INLINE get_connection() into connection()**

**Reasoning:**
- get_connection() only wraps sqlite3.connect() with error message reformatting
- Single-use function with minimal logic adds unnecessary indirection
- connection() context manager already has comprehensive exception handling (rollback, cleanup)
- Inlining simplifies the code while maintaining all functionality
- No testability or maintainability loss from inlining
