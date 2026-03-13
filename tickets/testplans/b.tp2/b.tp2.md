---
id: b.tp2
type: bee
title: "Test: spawn_agent"
parent: null
children: []
up_dependencies: []
egg: null
created_at: '2026-03-12T22:00:00.000000'
status: pupa
schema_version: '0.1'
---

## Setup
Run: `mkdir -p /tmp/waggle-test-spawn`

## Steps
1. Call `spawn_agent(repo="/tmp/waggle-test-spawn", session_name="waggle-test-spawn", agent="claude")`
2. Save the returned `session_id`
3. Call `list_agents` with no parameters

## Expected Response (spawn_agent)
- `status` equals `"success"`
- `session_id` is a non-empty string (tmux format, e.g. `"$3"`)
- `session_name` equals `"waggle-test-spawn"`
- `message` is a string

## Expected Response (list_agents verification)
- The `agents` array contains an entry where `session_name == "waggle-test-spawn"` or `name == "waggle-test-spawn"`

## Pass Criteria
- spawn_agent returns `status == "success"` AND `session_id` is non-empty AND session appears in list_agents

## Fail Criteria
- Any exception
- `status` is not `"success"`
- `session_id` is missing or empty
- Session not found in list_agents

## Teardown
Call `close_session(session_id=<saved_session_id>, force=true)`
