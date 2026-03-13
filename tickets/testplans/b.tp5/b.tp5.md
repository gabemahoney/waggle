---
id: b.tp5
type: bee
title: "Test: close_session"
parent: null
children: []
up_dependencies: []
egg: null
created_at: '2026-03-12T22:00:00.000000'
status: pupa
schema_version: '0.1'
---

## Setup
Run: `mkdir -p /tmp/waggle-test-close`
Call `spawn_agent(repo="/tmp/waggle-test-close", session_name="waggle-test-close", agent="claude")`. Save the returned `session_id`.

## Steps
1. Call `close_session(session_id=<saved_session_id>, force=true)`
2. Call `list_agents` with no parameters

## Expected Response (close_session)
- `status` equals `"success"`
- `message` is a string

## Expected Response (list_agents verification)
- The `agents` array does NOT contain any entry with `session_id == <saved_session_id>`

## Pass Criteria
- close_session returns `status == "success"` AND session no longer appears in list_agents

## Fail Criteria
- Any exception
- `status` is not `"success"`
- Session still present in list_agents after close

## Teardown
None (session already closed in test steps)
