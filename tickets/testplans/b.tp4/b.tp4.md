---
id: b.tp4
type: bee
title: "Test: check_status"
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
2. Call `check_status` with that `worker_id`

## Expected Response
Response contains `worker_id` (string), `status` (string — one of "spawning", "working", "waiting", "done", "error"), `model` (string), `repo` (string)

## Pass Criteria
Response contains `worker_id` matching the input AND `status` is one of the valid states

## Fail Criteria
Any exception raised, `worker_id` missing, or `status` is not a recognized value

## Teardown
None
