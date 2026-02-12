---
id: features.bees-2iq
type: t2
title: Add duplicate detection and removal logic to cleanup_dead_sessions()
down_dependencies:
- features.bees-tgu
- features.bees-wn1
- features.bees-jkf
parent: features.bees-fp8
created_at: '2026-02-11T23:39:33.515795'
updated_at: '2026-02-11T23:43:15.077960'
status: closed
bees_version: '1.1'
---

Modify `cleanup_dead_sessions()` in `/Users/gmahoney/projects/waggle/src/waggle/server.py` (lines 296-346):

**Context**: When tmux sessions operate in different directories, multiple state entries persist for same session (e.g., `/old/path:test+$3+...` and `/new/path:test+$3+...`), causing stale data and unpredictable lookups.

**Requirements**:
- Add duplicate detection logic after orphaned entry cleanup
- Query: `SELECT key, ROWID FROM state`
- Parse composite key from state key format: `{namespace}:name+session_id+session_created`
- Group entries by composite key (`name+session_id+session_created`)
- For each composite key with multiple entries, keep entry with max(ROWID) (most recent), delete others
- Use SQLite DELETE with ROWID to remove duplicates

**Success Criteria**:
- After cleanup runs, no duplicate entries exist for same session
- Only the most recent namespace entry is retained for each unique session
- Cleanup logic runs after orphaned entry cleanup in function flow

**Parent Epic**: features.bees-fp8
