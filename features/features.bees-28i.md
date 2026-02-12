---
id: features.bees-28i
type: t1
title: 'Refactor: Remove namespace from DB key, add repo as separate field'
down_dependencies:
- features.bees-gbf
- features.bees-2nh
parent: features.bees-86c
children:
- features.bees-ur5
- features.bees-m25
- features.bees-b49
- features.bees-seq
- features.bees-2jc
- features.bees-gzb
- features.bees-aar
- features.bees-rnv
- features.bees-t64
- features.bees-c7g
created_at: '2026-02-12T08:09:19.799250'
updated_at: '2026-02-12T09:55:43.756087'
priority: 1
status: completed
bees_version: '1.1'
---

Current architecture embeds repo path in the composite PRIMARY KEY:
- Key format: `{namespace}:{name}+{session_id}+{created}`
- When agent moves directories, old key is orphaned
- Requires cleanup logic to detect and remove orphaned entries

Proposed architecture:
- Key format: `{name}+{session_id}+{created}` (session identity only)
- Add separate `repo` column to store current working directory
- Agent updates this field on every state update
- Session identity persists across directory changes
- No need for orphan cleanup logic

Schema change:
```sql
CREATE TABLE state (
    key TEXT PRIMARY KEY,      -- {name}+{session_id}+{created}
    repo TEXT NOT NULL,         -- current working directory (from pwd)
    status TEXT NOT NULL,       -- agent state (working, waiting, etc)
    updated_at TIMESTAMP        -- last update time
)
```

This blocks the other tasks since they assume the current key structure.
