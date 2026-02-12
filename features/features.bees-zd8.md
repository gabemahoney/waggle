---
id: features.bees-zd8
type: t2
title: Remove namespace filter from database query in list_agents()
down_dependencies:
- features.bees-m3k
- features.bees-6hg
- features.bees-wto
parent: features.bees-3d5
created_at: '2026-02-11T23:39:31.071390'
updated_at: '2026-02-11T23:46:54.291327'
status: completed
bees_version: '1.1'
---

Context: Currently the database query filters by namespace (line 197-199), limiting results to only agents in the current directory. We need to show all agents system-wide.

What to Do:
- Modify the SQL query at line 198-199 in `/Users/gmahoney/projects/waggle/src/waggle/server.py`
- Change from: `SELECT key, value FROM state WHERE key LIKE ?` with `(f"{namespace}:%",)`
- Change to: `SELECT key, value FROM state`
- Remove the WHERE clause and parameter tuple entirely

Why: This allows the function to retrieve state entries for all agents across all namespaces, not just the current one.

Acceptance Criteria:
- Database query retrieves all state entries regardless of namespace
- No syntax errors in the modified SQL query
- Query still returns key-value pairs in the same format
