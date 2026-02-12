---
id: features.bees-3rb
type: t2
title: Update list_agents tests to remove repo_root parameter
down_dependencies:
- features.bees-sm0
parent: features.bees-gbf
created_at: '2026-02-12T08:20:11.334989'
updated_at: '2026-02-12T10:08:49.837140'
status: completed
bees_version: '1.1'
---

Update all test cases in tests/test_server.py that call list_agents to remove repo_root parameter.

**Context**: After removing repo_root parameter from list_agents function signature, all test calls must be updated to remove this parameter.

**Changes**:
- Review all 18 test cases that call list_agents (test_list_agents_* functions)
- Remove repo_root parameter from all list_agents() calls in these tests
- Ensure tests still pass after parameter removal

**Files**: tests/test_server.py:366-1092

**Acceptance**: All test cases call list_agents without repo_root parameter, tests compile without errors
