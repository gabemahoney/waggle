---
id: features.bees-o8d
type: t2
title: Add source-of-truth comment to hooks/set_state.sh
parent: features.bees-3wj
created_at: '2026-02-12T12:30:11.227603'
updated_at: '2026-02-12T12:38:07.485149'
priority: 0
status: completed
bees_version: '1.1'
---

Add comment above the CREATE TABLE block (line ~79) pointing to src/waggle/schema.sql as the source of truth:

```bash
# SCHEMA SOURCE OF TRUTH: src/waggle/schema.sql — keep in sync
```

Files: hooks/set_state.sh
