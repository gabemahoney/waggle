---
id: b.tp8
type: bee
title: "Test: answer_question"
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
2. Call `answer_question` with that `worker_id` and `answer="CI test answer"`

## Expected Response
Response contains `worker_id` and `delivered: true` on success. If no question is pending, response contains `error: "no_pending_question"` which is acceptable.

## Pass Criteria
Response contains (`worker_id` AND `delivered == true`) OR (`error == "no_pending_question"`)

## Fail Criteria
Any unexpected exception raised, or response contains an `error` value other than `"no_pending_question"`

## Teardown
None
