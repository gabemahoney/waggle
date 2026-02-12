---
id: features.bees-aq3
type: subtask
title: Delete run_hook() function from tests/test_hooks.py:126-192
parent: features.bees-iq1
created_at: '2026-02-12T11:48:06.875577'
updated_at: '2026-02-12T11:59:13.112968'
status: completed
bees_version: '1.1'
---

Context: run_hook() at lines 126-192 is dead code that was used before the hook was refactored to accept CLI arguments instead of stdin. It's never called anywhere.

What to do:
- Delete the run_hook() function definition from tests/test_hooks.py:126-192
- Verify run_set_state_hook() at line 65 remains and is the active hook runner

Files: tests/test_hooks.py

Acceptance: run_hook() function is removed from the file
