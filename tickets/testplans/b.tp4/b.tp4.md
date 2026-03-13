---
id: b.tp4
type: bee
title: "Test: send_command"
parent: null
children: []
up_dependencies: []
egg: null
created_at: '2026-03-12T22:00:00.000000'
status: pupa
schema_version: '0.1'
---

## Setup
Run: `mkdir -p /tmp/waggle-test-send`
Call `spawn_agent(repo="/tmp/waggle-test-send", session_name="waggle-test-send", agent="claude")`. Save the returned `session_id`.

## Steps
1. Poll `read_pane(session_id=<saved_session_id>)` up to 20 times with 3-second intervals until `agent_state == "done"`. If `done` state is not reached after 60 seconds total, fail the test immediately.
2. Call `send_command(session_id=<saved_session_id>, command="say hello")`

## Expected Response (send_command)
- `status` equals `"success"`
- `message` is a string (e.g. "command delivered")

## Pass Criteria
- send_command returns `status == "success"`

## Fail Criteria
- Any exception
- `status` is not `"success"`
- `agent_state == "done"` not reached within 60 seconds

## Teardown
Call `close_session(session_id=<saved_session_id>, force=true)`
