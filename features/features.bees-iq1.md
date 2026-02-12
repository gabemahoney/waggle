---
id: features.bees-iq1
type: task
title: Remove run_hook() dead function from tests/test_hooks.py
parent: features.bees-02t
children:
- features.bees-aq3
- features.bees-3gs
- features.bees-fo1
created_at: '2026-02-12T11:47:13.664592'
updated_at: '2026-02-12T12:16:19.403451'
priority: 0
status: completed
bees_version: '1.1'
---

Context: The run_hook() function at lines 126-192 is dead code - it's never called. It was used before the hook was refactored to accept CLI arguments instead of stdin.

What Needs to Change:
- Delete run_hook() function from tests/test_hooks.py:126-192
- Verify run_set_state_hook() at line 65 is the only hook runner in use
- Run tests to ensure nothing breaks

Files: tests/test_hooks.py

Bee: features.bees-02t

Success Criteria:
- run_hook() function is removed
- All tests pass
- No references to run_hook() remain in codebase
