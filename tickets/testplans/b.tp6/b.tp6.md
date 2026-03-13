---
id: b.tp6
type: bee
title: "Test: delete_repo_agents"
parent: null
children: []
up_dependencies: []
egg: null
created_at: '2026-03-12T22:00:00.000000'
status: pupa
schema_version: '0.1'
---

## Setup
Create stale DB row via sqlite3:
```bash
sqlite3 ~/.waggle/agent_state.db "CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, repo TEXT NOT NULL, status TEXT NOT NULL, updated_at TIMESTAMP);"
sqlite3 ~/.waggle/agent_state.db "INSERT OR REPLACE INTO state (key, repo, status, updated_at) VALUES ('waggle-test-stale+test+0', '/tmp/waggle-test-delete', 'stale', CURRENT_TIMESTAMP);"
```
This creates a fake stale DB row for repo path `/tmp/waggle-test-delete`.

## Steps
1. Call `delete_repo_agents(repo_root="/tmp/waggle-test-delete")`

## Expected Response
- `status` equals `"success"`
- `deleted_count` is an integer >= 1

## Pass Criteria
- `status == "success"` AND `deleted_count >= 1`

## Fail Criteria
- Any exception
- `status` is not `"success"`
- `deleted_count` < 1

## Teardown
Run: `sqlite3 ~/.waggle/agent_state.db "DELETE FROM state WHERE repo = '/tmp/waggle-test-delete';"`
