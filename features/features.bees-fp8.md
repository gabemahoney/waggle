---
id: features.bees-fp8
type: t1
title: Add duplicate cleanup to cleanup_dead_sessions()
parent: features.bees-0je
children:
- features.bees-2iq
- features.bees-tgu
- features.bees-wn1
- features.bees-jkf
- features.bees-j3b
created_at: '2026-02-11T23:38:43.657726'
updated_at: '2026-02-11T23:44:30.453699'
priority: 0
status: closed
bees_version: '1.1'
---

Context: When a tmux session operates in different directories over time, multiple state entries persist (e.g., `/old/path:test+$3+...` and `/new/path:test+$3+...`). This causes stale data and unpredictable status lookups.

What Needs to Change:
- Modify `cleanup_dead_sessions()` in `/Users/gmahoney/projects/waggle/src/waggle/server.py` (lines 296-346)
- Add duplicate detection logic after orphaned entry cleanup
- Query: `SELECT key, ROWID FROM state`
- Group by composite key (extract from `namespace:composite_key` format)
- For each composite key with multiple entries, keep only max(ROWID), delete others

Why: Ensures each active session has only one canonical state entry with the most recent namespace.

Success Criteria:
- After cleanup runs, no duplicate entries exist for same session (same composite key)
- Existing tests pass
- New test validates duplicate removal

Files: /Users/gmahoney/projects/waggle/src/waggle/server.py
Bee: features.bees-0je
