---
id: b.tp6
type: bee
title: "Test: send_input"
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
2. Call `send_input` with that `worker_id` and `text="hello from CI test"`

## Expected Response
Response contains `worker_id` and `delivered: true` on success. If the worker has not connected its MCP session yet (common in CI), response contains `error: "worker_not_connected"` which is acceptable.

## Pass Criteria
Response contains (`worker_id` AND `delivered == true`) OR (`error == "worker_not_connected"`)

## Fail Criteria
Any unexpected exception raised, or response contains an `error` value other than `"worker_not_connected"`

## Teardown
None
