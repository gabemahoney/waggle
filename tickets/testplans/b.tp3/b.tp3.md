---
id: b.tp3
type: bee
title: "Test: read_pane"
parent: null
children: []
up_dependencies: []
egg: null
created_at: '2026-03-12T22:00:00.000000'
status: pupa
schema_version: '0.1'
---

## Setup
Run: `mkdir -p /tmp/waggle-test-read`
Call `spawn_agent(repo="/tmp/waggle-test-read", session_name="waggle-test-read", agent="claude")`. Save the returned `session_id`.

## Steps
1. Poll `read_pane(session_id=<saved_session_id>)` up to 10 times with 3-second intervals until `agent_state` is not `"unknown"`, OR accept any non-error response after at least 1 successful call

## Expected Response
- `status` equals `"success"`
- `agent_state` is present and is one of: `"working"`, `"done"`, `"ask_user"`, `"check_permission"`, `"unknown"`
- `content` is present and is a string (may be empty)

## Pass Criteria
- `status == "success"` AND `agent_state` field is present AND `content` field is present

## Fail Criteria
- Any exception
- `status` is not `"success"`
- `agent_state` field is missing
- `content` field is missing

## Teardown
Call `close_session(session_id=<saved_session_id>, force=true)`
