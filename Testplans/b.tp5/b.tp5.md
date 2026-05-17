---
id: b.tp5
type: bee
title: "Test: get_output"
parent: null
children: []
up_dependencies: [b.tp2]
egg: null
created_at: '2026-04-28T00:00:00.000000'
status: pupa
schema_version: '0.1'
---

## Setup
A worker must be running (b.tp2 dependency ensures one was spawned).

## Steps
1. Call `list_workers` to get a `worker_id`
2. Call `get_output` with that `worker_id`

## Expected Response
Response contains `worker_id` (string), `lines` (string — the pane content, may be empty if worker just started)

## Pass Criteria
Response contains `worker_id` AND `lines` field is present (string, may be empty)

## Fail Criteria
Any exception raised, `worker_id` missing, or `lines` field missing

## Teardown
None
