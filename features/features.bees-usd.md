---
id: features.bees-usd
type: t3
title: Replace N individual DELETEs with single batch DELETE
down_dependencies:
- features.bees-bd8
- features.bees-whl
- features.bees-0ve
parent: features.bees-sh1
created_at: '2026-02-11T22:27:53.268164'
updated_at: '2026-02-11T23:20:23.384263'
status: closed
bees_version: '1.1'
---

In `server.py:336-348`, replace the loop of individual DELETE statements with a single batch DELETE operation.

## Files
- `src/waggle/server.py` lines 336-348

## Implementation
1. Collect all keys to delete
2. Use `DELETE FROM state WHERE key NOT IN (...)` or similar batch approach
3. Execute single SQL statement instead of N statements

## Acceptance
- Single batch DELETE replaces multiple individual DELETEs
- Same functional behavior maintained
