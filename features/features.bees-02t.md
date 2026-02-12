---
id: features.bees-02t
type: bee
title: Remove dead code and obsolete tests
children:
- features.bees-iq1
- features.bees-9rm
- features.bees-itu
- features.bees-4xb
created_at: '2026-02-12T11:45:22.860545'
updated_at: '2026-02-12T12:16:35.943926'
priority: 2
status: completed
bees_version: '1.1'
---

Clean up dead code, unused variables, and obsolete tests across the codebase:

## Dead Code

1. **run_hook() in tests/test_hooks.py:126-192**
   - Function defined but never called
   - Accepts stdin_json and pipes to hook, but set_state.sh takes CLI argument not stdin
   - Leftover from before hook was refactored to use $1 instead of stdin
   - run_set_state_hook() helper at line 65 is actually used

2. **composite_key = key in server.py:221**
   - Useless variable alias
   - Loop at line 218 iterates (key, repo_path, status) then assigns composite_key = key
   - Only composite_key is used in map, but key already is the composite key
   - Adds no value

3. **get_connection() in database.py:48-64**
   - Public API function only used internally by connection() context manager at line 87
   - Wraps sqlite3.connect() and re-raises same exception with marginally better message
   - Unnecessary indirection - should be private (_get_connection) or inlined

## Obsolete Tests

4. **3 skipped E2E tests in test_server.py**
   - Lines 1040, 1150, and 1328
   - @pytest.mark.skip(reason="Requires hook update (task features.bees-2jc)")
   - Reference 2-column schema (key TEXT PRIMARY KEY, value TEXT) that no longer exists
   - Hook already uses 4-column schema
   - Tests will never pass as written - they assert against old schema
