---
id: features.bees-b77
type: t1
title: Delete dead run_hook() function from test_hooks.py
parent: features.bees-n6y
created_at: '2026-02-12T12:09:45.145763'
updated_at: '2026-02-12T12:23:03.266204'
priority: 0
status: completed
bees_version: '1.1'
---

## What

Delete the `run_hook()` function at `tests/test_hooks.py:126-192`. It is 67 lines of dead code — defined but never called.

## Why

The function was written for an older version of `set_state.sh` that read JSON from stdin. The hook was refactored to take a CLI argument (`$1`) instead. The replacement helper `run_set_state_hook()` at line 65 is what every test actually uses.

## How

Delete lines 126-192 in `tests/test_hooks.py`. Run `poetry run pytest` to confirm nothing breaks.

## Files
- `tests/test_hooks.py`
