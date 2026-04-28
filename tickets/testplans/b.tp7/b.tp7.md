---
id: b.tp7
type: bee
title: "Test: approve_permission"
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
2. Call `approve_permission` with that `worker_id` and `decision="allow"`

## Expected Response
Response contains `status` field. If no permission is pending, response may contain `status: "no_pending_request"` which is acceptable.

## Pass Criteria
Response contains `status` field equal to `"ok"` OR `"no_pending_request"`

## Fail Criteria
Any exception raised or `status` is not one of the acceptable values

## Teardown
None
