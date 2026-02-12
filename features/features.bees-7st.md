---
id: features.bees-7st
type: t2
title: Add repo parameter to list_agents() function signature
parent: features.bees-3d5
created_at: '2026-02-11T23:39:35.305285'
updated_at: '2026-02-11T23:47:03.088575'
status: completed
bees_version: '1.1'
---

Context: Users need ability to filter agents by repository path. We need to add an optional parameter for this filtering.

What to Do:
- Modify the `list_agents()` function signature around line 122 in `/Users/gmahoney/projects/waggle/src/waggle/server.py`
- Add parameter: `repo: Optional[str] = None` after the `name` parameter
- Import `Optional` from typing at the top of the file if not already present

Why: This parameter will enable users to filter agents by repository path substring (implemented in subsequent subtasks).

Acceptance Criteria:
- Function signature includes `repo: Optional[str] = None` parameter
- Parameter is properly typed with Optional[str]
- No syntax errors in function signature
