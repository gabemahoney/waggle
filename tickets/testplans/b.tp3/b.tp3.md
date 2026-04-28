---
id: b.tp3
type: bee
title: "Test: list_workers"
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
1. Call `list_workers` with no parameters

## Expected Response
Response contains a `workers` field that is a JSON array with at least one entry. Each entry contains `worker_id` (string), `status` (string), `model` (string), `repo` (string)

## Pass Criteria
`workers` is a list with length >= 1, and each worker has `worker_id`, `status`, `model`, and `repo` fields

## Fail Criteria
Any exception raised, `workers` is missing or not a list, or list is empty

## Teardown
None
