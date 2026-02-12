---
id: features.bees-lq9
type: t3
title: Replace echo with printf for variable sanitization
down_dependencies:
- features.bees-8cq
- features.bees-18n
- features.bees-nct
parent: features.bees-9ru
created_at: '2026-02-11T22:28:03.798467'
updated_at: '2026-02-11T23:22:25.845762'
status: closed
bees_version: '1.1'
---

In `set_state.sh` lines 38-39, replace `echo "$KEY"` with `printf '%s' "$KEY"` and same for `$STATE`.

## Files
- `set_state.sh` lines 38-39

## Implementation
1. Replace `echo "$KEY"` with `printf '%s' "$KEY"`
2. Replace `echo "$STATE"` with `printf '%s' "$STATE"`
3. Ensures trailing newlines are not stripped

## Acceptance
- Shell script uses `printf '%s'` for all variable sanitization
- No trailing newline stripping occurs
