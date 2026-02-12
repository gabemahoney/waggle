---
id: features.bees-9ru
type: t2
title: Fix echo newline stripping in set_state.sh
parent: features.bees-dcu
children:
- features.bees-lq9
- features.bees-8cq
- features.bees-18n
- features.bees-nct
- features.bees-ysj
created_at: '2026-02-11T22:27:32.347036'
updated_at: '2026-02-11T23:23:34.577679'
status: closed
bees_version: '1.1'
---

Replace `echo "$KEY"` with `printf '%s' "$KEY"` in `set_state.sh` (lines 38-39) to prevent edge case where trailing newlines get stripped.

## Context
The `echo` command strips trailing newlines from variables, which can cause subtle bugs in state handling.

## Requirements
- Replace `echo "$KEY"` with `printf '%s' "$KEY"`
- Same for `$STATE` sanitization
- Prevents edge case where trailing newlines get stripped

## Acceptance Criteria
- Shell script uses `printf '%s'` for all variable sanitization
- No trailing newline stripping occurs
- `poetry run pytest` passes
