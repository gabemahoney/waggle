---
id: features.bees-seq
type: t2
title: Remove orphan cleanup logic from cleanup_dead_sessions
parent: features.bees-28i
created_at: '2026-02-12T08:20:58.126937'
updated_at: '2026-02-12T09:55:27.592431'
status: completed
bees_version: '1.1'
---

Simplify `cleanup_dead_sessions()` in `src/waggle/server.py` by removing orphan detection and duplicate removal logic.

**Context**: With the new schema, agents update their `repo` field on every state update, so there are no "orphaned" entries when agents move directories. Session identity persists across directory changes. The only cleanup needed is removing entries for terminated tmux sessions.

**Requirements**:
- Keep logic that queries active tmux sessions
- Keep logic that deletes entries for dead sessions (sessions not in tmux)
- Remove duplicate detection logic (lines 372-399)
- Remove composite key grouping and max ROWID selection
- Keep the function synchronous and silent (never raises exceptions)

**Files to Modify**:
- `src/waggle/server.py:cleanup_dead_sessions()` (lines 318-405)

**Logic to Remove**:
```python
# Remove this entire section (lines 372-399):
# - Query all remaining state entries with ROWIDs
# - Group entries by composite key
# - Find duplicates and keep only max ROWID
# - Batch delete duplicate entries
```

**Logic to Keep**:
- Query active tmux sessions (lines 326-346)
- Build active_sessions set of composite keys
- Query all database keys (lines 353-355)
- Find orphaned entries (dead sessions) (lines 358-365)
- Batch delete orphaned entries (lines 368-370)
- Commit changes (line 401)

**Acceptance**:
- cleanup_dead_sessions only deletes entries for dead tmux sessions
- No duplicate detection or ROWID queries remain
- Function is simpler and faster
- Error handling remains silent (no exceptions raised)
