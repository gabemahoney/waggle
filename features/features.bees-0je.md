---
id: features.bees-0je
type: bee
title: Fix list_agents to show all directories with namespace filtering
children:
- features.bees-fp8
- features.bees-3d5
created_at: '2026-02-11T23:10:00.867091'
updated_at: '2026-02-12T07:47:57.214912'
priority: 2
status: completed
bees_version: '1.1'
---

## Problem
Currently `waggle list` only shows agents in the current directory due to namespace filtering. Also, duplicate state entries can exist when a session operates in different directories over time.

## Requirements
1. **Remove namespace filter** from database query in `list_agents()`
2. **Add `repo` parameter** for optional case-insensitive substring filtering on namespace
3. **Add duplicate cleanup** to `cleanup_dead_sessions()` - detect duplicate entries for same session (same composite key but different namespaces), keep only newest based on ROWID, delete others
4. **Add `namespace` field** to output showing what repo the agent reported
5. **Filter sessions** to only show those with state entries matching repo substring (when repo param provided)
6. **Update docstring** to reflect new behavior

## Files to modify
- `/Users/gmahoney/projects/waggle/src/waggle/server.py`
  - `list_agents()` function (lines 123-235)
  - `cleanup_dead_sessions()` function (lines 296-346)

## Technical details
- State key format: `{namespace}:name+session_id+session_created`
- Use SQLite ROWID to determine newest entry (higher ROWID = more recently written)
- Duplicate detection: Group by composite key, keep max(ROWID) per group
