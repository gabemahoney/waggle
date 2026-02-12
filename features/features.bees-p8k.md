---
id: features.bees-p8k
type: t2
title: Create src/waggle/schema.sql with canonical DDL
parent: features.bees-3wj
created_at: '2026-02-12T12:30:06.209494'
updated_at: '2026-02-12T12:37:44.403055'
priority: 0
status: completed
bees_version: '1.1'
---

Create the canonical schema.sql file extracted from database.py:35-42.

Content:
```sql
CREATE TABLE IF NOT EXISTS state (
    key TEXT PRIMARY KEY,
    repo TEXT NOT NULL,
    status TEXT NOT NULL,
    updated_at TIMESTAMP
);
```

Files: src/waggle/schema.sql (new)
