---
id: features.bees-nrx
type: t2
title: Update database.py to read DDL from schema.sql file
parent: features.bees-3wj
created_at: '2026-02-12T12:30:08.661372'
updated_at: '2026-02-12T12:37:55.948050'
priority: 0
status: completed
bees_version: '1.1'
---

Modify init_schema() to read DDL from schema.sql instead of inline string. Use Path(__file__).parent / "schema.sql" to locate the file. Function signature and behavior remain identical.

Files: src/waggle/database.py
