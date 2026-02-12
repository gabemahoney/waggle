---
id: features.bees-2wz
type: t1
title: Remove pointless composite_key = key alias in server.py
parent: features.bees-n6y
created_at: '2026-02-12T12:10:00.478394'
updated_at: '2026-02-12T12:23:03.964160'
priority: 0
status: completed
bees_version: '1.1'
---

## What

In `src/waggle/server.py:218-222`, the loop assigns `composite_key = key` then only uses `composite_key`. The alias adds nothing — `key` from the database row already *is* the composite key.

```python
# Before
for key, repo_path, status in state_entries:
    composite_key = key
    state_map[composite_key] = (repo_path, status)

# After
for key, repo_path, status in state_entries:
    state_map[key] = (repo_path, status)
```

Also delete the two comments above it (lines 219-220) that explain the key format — they duplicate the docstring in `database.py:22` and the comment in `set_state.sh:34`.

## Files
- `src/waggle/server.py`
