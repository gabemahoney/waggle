---
id: features.bees-ufz
type: t2
title: Remove redundant len(roots) == 0 check from server.py:47
down_dependencies:
- features.bees-kqv
- features.bees-xjt
- features.bees-nqh
parent: features.bees-23k
created_at: '2026-02-12T12:24:28.223538'
updated_at: '2026-02-12T12:28:35.439831'
status: completed
bees_version: '1.1'
---

## Context
Line 47 in `src/waggle/server.py` has a redundant condition check. The expression `if not roots or len(roots) == 0:` is redundant because `not roots` already evaluates to `True` for both `None` and empty lists.

## What to do
1. Open `src/waggle/server.py`
2. Navigate to line 47
3. Change `if not roots or len(roots) == 0:` to `if not roots:`
4. Save the file

## Files
- `src/waggle/server.py` (line 47)

## Acceptance
- Line 47 contains only `if not roots:` with no `len()` check
- Code logic remains unchanged (both `None` and empty list still return `None`)
