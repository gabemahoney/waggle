---
id: features.bees-vdq
type: subtask
title: Remove unused source variable in resolve_repo_root
parent: features.bees-1qh
created_at: '2026-02-11T22:26:59.054246'
updated_at: '2026-02-11T22:41:52.395388'
status: completed
bees_version: '1.1'
---

**Context**: The `resolve_repo_root` function has an unused `source` variable.

**What to do**:
- Locate the `source` variable assignment in `resolve_repo_root` function
- Remove the unused variable assignment

**Acceptance**: No unused `source` variable in resolve_repo_root function.
