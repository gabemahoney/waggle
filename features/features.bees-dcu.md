---
id: features.bees-dcu
type: t1
title: Subprocess and Shell Script Hardening
parent: features.bees-f8i
children:
- features.bees-zil
- features.bees-sh1
- features.bees-9ru
created_at: '2026-02-11T22:26:59.230955'
updated_at: '2026-02-11T23:36:28.727575'
priority: 0
status: completed
bees_version: '1.1'
---

Fix three subprocess/shell reliability issues: missing timeout, inefficient batch deletion, and echo newline stripping.

## Work Items

1. **Add timeout to tmux subprocess in `list_agents`** (`server.py:153-158`)
   - Add `timeout=5` to `subprocess.run()` call
   - Matches pattern already used in `cleanup_dead_sessions`

2. **Improve `cleanup_dead_sessions` efficiency** (`server.py:336-348`)
   - Replace N individual DELETE statements with single batch DELETE
   - Use `DELETE FROM state WHERE key NOT IN (...)` or build key set

3. **Fix `echo` newline stripping in `set_state.sh`** (lines 38-39)
   - Replace `echo "$KEY"` with `printf '%s' "$KEY"`
   - Same for `$STATE` sanitization
   - Prevents edge case where trailing newlines get stripped

## Success Criteria
- `list_agents` has 5-second timeout matching `cleanup_dead_sessions` pattern
- `cleanup_dead_sessions` uses single batch DELETE operation
- Shell script uses printf for all variable sanitization
- `poetry run pytest` passes
