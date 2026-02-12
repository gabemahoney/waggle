---
id: features.bees-3se
type: subtask
title: Remove dead hook fixtures from conftest.py
down_dependencies:
- features.bees-rs1
- features.bees-wm2
- features.bees-zr0
- features.bees-ti9
- features.bees-l02
parent: features.bees-a4i
created_at: '2026-02-11T22:26:52.547501'
updated_at: '2026-02-11T22:48:27.604574'
status: completed
bees_version: '1.1'
---

**Context**: Test fixtures reference hooks that no longer exist in the codebase.

**What to do**:
- Open `tests/conftest.py`
- Remove these fixtures: `stop_hook`, `permission_request_hook`, `notification_hook`, `session_start_hook`
- Ensure no other tests depend on these fixtures (they shouldn't since the hooks don't exist)

**Acceptance**: conftest.py no longer contains these four fixture definitions.
