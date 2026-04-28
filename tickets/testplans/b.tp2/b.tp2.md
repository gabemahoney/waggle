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
Response contains `status` field equal to `"ok"` and a `worker_id` field (string UUID)

## Pass Criteria
`status == "ok"` AND `worker_id` is a non-empty string

## Fail Criteria
Any exception raised, `status` is not `"ok"`, or `worker_id` is missing

## Teardown
None (worker stays alive for downstream tests; tp9 handles termination)
