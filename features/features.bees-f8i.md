---
id: features.bees-f8i
type: bee
title: Database robustness improvements
labels:
- database
- bugfix
children:
- features.bees-r2u
- features.bees-dcu
created_at: '2026-02-11T22:24:52.880706'
updated_at: '2026-02-11T23:36:27.371556'
priority: 2
status: completed
bees_version: '1.1'
---

Fix database-related bugs and improve robustness identified in code review.

## Work Items

1. **Fix race condition in `cleanup_all_agents`** (`server.py:270-281`)
   - Use `cursor.rowcount` after DELETE instead of separate COUNT query
   - Eliminates race between COUNT and DELETE

2. **Add timeout to tmux subprocess in `list_agents`** (`server.py:153-158`)
   - Add `timeout=5` to `subprocess.run()` call
   - Matches pattern already used in `cleanup_dead_sessions`

3. **Add explicit rollback in `connection()` context manager** (`database.py:63-86`)
   - Call `conn.rollback()` on exception before close
   - Makes error handling explicit rather than relying on SQLite auto-rollback

4. **Improve `cleanup_dead_sessions` efficiency** (`server.py:336-348`)
   - Replace N individual DELETE statements with single batch DELETE
   - Use `DELETE FROM state WHERE key NOT IN (...)` or build key set

5. **Fix `echo` newline stripping in `set_state.sh`** (lines 38-39)
   - Replace `echo "$KEY"` with `printf '%s' "$KEY"`
   - Same for `$STATE` sanitization
   - Prevents edge case where trailing newlines get stripped

## Verification

- `poetry run pytest` passes
- End-to-end test: spawn agent, check state, kill agent, verify cleanup
