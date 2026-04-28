---
id: b.tp9
type: bee
title: "Test: terminate_worker"
parent: null
children: []
up_dependencies: [b.tp3, b.tp4, b.tp5, b.tp6, b.tp7, b.tp8]
egg: null
created_at: '2026-04-28T00:00:00.000000'
status: pupa
schema_version: '0.1'
---

## Setup
A worker must be running from previous tests.

## Steps
1. Call `list_workers` to get a `worker_id`
2. Call `terminate_worker` with that `worker_id`
3. Call `list_workers` again to confirm the worker is gone

## Expected Response
Step 2 response contains `status` field equal to `"ok"`. Step 3 response `workers` list does not contain the terminated `worker_id`.

## Pass Criteria
terminate_worker returns `status == "ok"` AND subsequent list_workers does not include the worker

## Fail Criteria
Any exception raised, `status` is not `"ok"`, or worker still appears in list_workers after termination

## Teardown
None (worker is already terminated)
