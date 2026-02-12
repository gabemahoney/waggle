---
id: features.bees-23k
type: t1
title: Remove redundant len(roots) == 0 check in server.py
parent: features.bees-n6y
children:
- features.bees-ufz
- features.bees-kqv
- features.bees-xjt
- features.bees-nqh
- features.bees-bue
created_at: '2026-02-12T12:13:00.414954'
updated_at: '2026-02-12T12:28:39.377469'
priority: 0
status: completed
bees_version: '1.1'
---

## What

`src/waggle/server.py:33` has a redundant check:

```python
if not roots or len(roots) == 0:
```

`not roots` already handles both `None` and empty list. The `len()` check adds nothing.

## How

Change to `if not roots:`. Run `poetry run pytest` to confirm.

## Files
- `src/waggle/server.py`
