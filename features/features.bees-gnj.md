---
id: features.bees-gnj
type: t2
title: Create tests/test_schema_conformance.py with drift detection
parent: features.bees-3wj
created_at: '2026-02-12T12:30:15.668840'
updated_at: '2026-02-12T12:38:29.570073'
priority: 0
status: completed
bees_version: '1.1'
---

Create conformance test that:
1. Parses src/waggle/schema.sql to extract column names, types, and constraints
2. Reads hooks/set_state.sh and extracts its CREATE TABLE statement
3. Asserts the hook's column names, types, and constraints match schema.sql
4. Extracts the INSERT OR REPLACE column list from the hook and asserts it references the same columns in the same order as schema.sql

Use simple regex/string matching for parsing. These are small, well-structured SQL statements.

Files: tests/test_schema_conformance.py (new)
