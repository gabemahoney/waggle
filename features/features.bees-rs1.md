---
id: features.bees-rs1
type: subtask
title: Remove TestHookDescriptiveStates class
up_dependencies:
- features.bees-3se
parent: features.bees-a4i
created_at: '2026-02-11T22:26:57.722410'
updated_at: '2026-02-11T22:48:28.385357'
status: completed
bees_version: '1.1'
---

**Context**: TestHookDescriptiveStates tests hooks that no longer exist.

**What to do**:
- Find and open the test file containing `TestHookDescriptiveStates` class
- Remove the entire class
- If the file becomes empty, delete it

**Acceptance**: No `TestHookDescriptiveStates` class in the test suite.
