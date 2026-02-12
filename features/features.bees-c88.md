---
id: features.bees-c88
type: t3
title: Run unit tests and fix failures
up_dependencies:
- features.bees-mur
parent: features.bees-5bs
created_at: '2026-02-12T15:15:58.109933'
updated_at: '2026-02-12T15:22:47.274873'
status: completed
bees_version: '1.1'
---

**Context**: Task refactored list_agents function and updated related tests.

**Requirements**: 
- Execute full test suite for waggle
- Fix any test failures related to list_agents changes
- Ensure 100% pass rate, even if issues appear pre-existing
- Verify list_agents behavior matches requirements (DB-first, no "unknown" status)

**Acceptance**: All tests pass successfully
