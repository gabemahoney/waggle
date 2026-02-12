---
id: features.bees-wm2
type: subtask
title: Fix TestConfigReading tests to use set_state_hook
up_dependencies:
- features.bees-3se
parent: features.bees-a4i
created_at: '2026-02-11T22:27:03.293727'
updated_at: '2026-02-11T22:48:29.141084'
status: completed
bees_version: '1.1'
---

**Context**: TestConfigReading tests use `stop_hook` fixture which no longer exists.

**What to do**:
- Find `TestConfigReading` class in test files
- Replace `stop_hook` fixture references with `set_state_hook`
- Update any assertions that depend on the hook type
- Ensure tests still validate the config reading functionality

**Acceptance**: TestConfigReading tests pass using `set_state_hook` fixture.
