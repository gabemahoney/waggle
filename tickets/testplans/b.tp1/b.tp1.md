---
id: b.tp1
type: bee
title: "Test: register_caller"
parent: null
children: []
up_dependencies: []
egg: null
created_at: '2026-04-28T00:00:00.000000'
status: pupa
schema_version: '0.1'
---

## Setup
No setup required.

## Steps
1. Call `register_caller` with `caller_type="local"`

## Expected Response
Response contains `status` field equal to `"ok"` and a `caller_id` field (string)

## Pass Criteria
`status == "ok"` AND `caller_id` is a non-empty string

## Fail Criteria
Any exception raised, `status` is not `"ok"`, or `caller_id` is missing/empty

## Teardown
None
