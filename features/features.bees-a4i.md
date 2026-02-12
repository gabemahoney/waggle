---
id: features.bees-a4i
type: task
title: Fix broken test references and delete dead test script
down_dependencies:
- features.bees-9yk
parent: features.bees-c5g
children:
- features.bees-3se
- features.bees-rs1
- features.bees-wm2
- features.bees-8zz
- features.bees-zr0
- features.bees-ti9
- features.bees-l02
- features.bees-jaz
created_at: '2026-02-11T22:26:21.731647'
updated_at: '2026-02-11T22:52:34.735478'
priority: 0
status: completed
bees_version: '1.1'
---

**Context**: Tests reference non-existent hooks and a dead test script references a deleted config.sh.

**What Needs to Change**:
- Remove fixtures: `stop_hook`, `permission_request_hook`, `notification_hook`, `session_start_hook`
- Remove `TestHookDescriptiveStates` class
- Fix `TestConfigReading` tests that use `stop_hook` (use `set_state_hook` instead)
- Delete `tests/scripts/test_config.sh`

**Why**: Tests for removed functionality cause confusion and potential false positives.

**Success Criteria**:
- No references to dead hook fixtures
- `poetry run pytest` passes with all tests valid
