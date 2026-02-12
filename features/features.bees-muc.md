---
id: features.bees-muc
type: task
title: Remove validate.py module and entry point
down_dependencies:
- features.bees-9yk
parent: features.bees-c5g
children:
- features.bees-vyw
- features.bees-ejo
- features.bees-hi5
- features.bees-9e3
- features.bees-29n
- features.bees-uz4
created_at: '2026-02-11T22:26:16.635828'
updated_at: '2026-02-11T22:52:34.728563'
priority: 0
status: completed
bees_version: '1.1'
---

**Context**: The `validate.py` module and `waggle-validate` CLI entry point are dead code - no longer used in the system.

**What Needs to Change**:
- Delete `src/waggle/validate.py` 
- Remove `waggle-validate` from `pyproject.toml` scripts section

**Why**: Reduces codebase size and eliminates confusion from unused code.

**Success Criteria**:
- `src/waggle/validate.py` no longer exists
- `waggle-validate` not in pyproject.toml
- `poetry run pytest` passes
