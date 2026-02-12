---
id: features.bees-to8
type: t2
title: Review unit tests for this Epic. See if you need to update, delete or add any.
up_dependencies:
- features.bees-ijm
parent: features.bees-gbf
created_at: '2026-02-12T08:20:24.616310'
updated_at: '2026-02-12T10:13:39.510734'
status: completed
bees_version: '1.1'
---

Review existing unit tests for list_agents to determine if additional test coverage is needed after parameter removal.

**Context**: After removing repo_root parameter, verify that existing tests adequately cover the list_agents functionality and that no new test cases are needed.

**Test areas to review**:
- Verify all existing tests still provide adequate coverage
- Check if any tests were specifically testing repo_root behavior that should now be removed
- Determine if any new tests are needed

**Files**: tests/test_server.py:366-1092

**Acceptance**: Test coverage reviewed, new tests added if needed, or confirmed existing tests are sufficient
