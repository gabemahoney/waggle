---
id: features.bees-n2q
type: t2
title: Replace hardcoded DDL in test_hooks.py with init_schema() calls
parent: features.bees-3wj
created_at: '2026-02-12T12:30:19.270274'
updated_at: '2026-02-12T12:39:23.501621'
priority: 0
status: completed
bees_version: '1.1'
---

Replace the 2 non-skipped hardcoded CREATE TABLE calls in tests/test_hooks.py (lines 458, 680) with:

```python
from waggle.database import init_schema
init_schema(db_path)
```

Leave the 5 instances in skipped E2E tests alone (they reference the old 2-column schema and are dead code).

Files: tests/test_hooks.py
