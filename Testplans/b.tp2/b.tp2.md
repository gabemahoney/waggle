---
id: b.tp2
type: bee
title: "Test: spawn_worker"
parent: null
children: []
up_dependencies: [b.tp1]
egg: null
created_at: '2026-04-28T00:00:00.000000'
status: pupa
schema_version: '0.1'
---

## Setup
Ensure register_caller has been called (b.tp1 dependency handles this).

## Steps
1. Call `spawn_worker` with `model="sonnet"`, `repo="/tmp/waggle-test-spawn"`, `session_name="ci-test-spawn"`

## Expected Response
Response contains a `worker_id` field (non-empty string UUID) and a `session_name` field (string)

## Pass Criteria
`worker_id` is a non-empty string AND `session_name` is a non-empty string

## Fail Criteria
Any exception raised, `worker_id` is missing, or response contains an `error` field

## Teardown
None (worker stays alive for downstream tests; tp9 handles termination)
