---
id: features.bees-sh1
type: t2
title: Improve cleanup_dead_sessions efficiency with batch DELETE
parent: features.bees-dcu
children:
- features.bees-usd
- features.bees-bd8
- features.bees-whl
- features.bees-0ve
- features.bees-pps
created_at: '2026-02-11T22:27:29.473752'
updated_at: '2026-02-11T23:21:14.404678'
status: closed
bees_version: '1.1'
---

Replace N individual DELETE statements with a single batch DELETE operation in `cleanup_dead_sessions` (`server.py:336-348`).

## Context
Currently the function issues individual DELETE statements for each dead session, which is inefficient for large numbers of stale entries.

## Requirements
- Replace N individual DELETE statements with single batch DELETE
- Use `DELETE FROM state WHERE key NOT IN (...)` or build key set
- Maintain same functional behavior

## Acceptance Criteria
- Single batch DELETE replaces multiple individual DELETEs
- Dead sessions are still correctly cleaned up
- `poetry run pytest` passes
