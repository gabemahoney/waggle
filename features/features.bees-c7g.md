---
id: features.bees-c7g
type: t2
title: Fix test_opencode_integration.py to use new schema
parent: features.bees-28i
created_at: '2026-02-12T09:45:06.589886'
updated_at: '2026-02-12T09:53:08.591288'
priority: 1
status: closed
bees_version: '1.1'
---

Update test_opencode_integration.py to use new database schema with repo/status columns instead of old value column, and new key format without namespace prefix.

Changes needed:
1. Line 50: Change `SELECT key, value` to `SELECT key, repo, status`
2. Lines 86, 97, 108: Change `SELECT value` to `SELECT status`
3. Line 60: Update assertion for new key format (no `:` separator)
4. Line 59: Remove assertion checking for namespace in key
5. Verify all tests pass after updates

Files: tests/test_opencode_integration.py
