---
id: b.tp1
type: bee
title: "Test: list_agents"
parent: null
children: []
up_dependencies: []
egg: null
created_at: '2026-03-12T22:00:00.000000'
status: pupa
schema_version: '0.1'
---

## Setup
No setup required. The test is valid even if no waggle-managed sessions are active.

## Steps
1. Call `list_agents` with no parameters

## Expected Response
- `status` equals `"success"`
- `agents` is a JSON array (may be empty)
- Each agent object (if any) contains: `name` (string), `session_id` (string), `status` (string), `repo` (string), `directory` (string)

## Pass Criteria
- `status == "success"` AND `agents` is a list (including empty list)

## Fail Criteria
- Any exception raised
- `status` is not `"success"`
- `agents` field is missing or not a list

## Teardown
None
