---
id: features.bees-kf9
type: t1
title: Change sanitization failure exits from exit 1 to exit 0 in set_state.sh
parent: features.bees-n6y
children:
- features.bees-9ek
- features.bees-bq0
- features.bees-l92
- features.bees-29z
created_at: '2026-02-12T12:15:02.392024'
updated_at: '2026-02-12T12:29:49.387842'
priority: 0
status: completed
bees_version: '1.1'
---

## What

`hooks/set_state.sh` lines 60-63, 66-68, and 71-74 exit with `exit 1` when sanitization fails. This contradicts the hook's "never block the agent" design (the script ends with `exit 0` and redirects sqlite3 stderr to `/dev/null`).

## How

Change the three `exit 1` to `exit 0`. If sanitization fails, the hook silently skips the DB write and returns success. No unsanitized data reaches SQLite.

## Files
- `hooks/set_state.sh`
