---
id: features.bees-tb7
type: t2
title: Review unit tests for this Epic. See if you need to update, delete or add any.
up_dependencies:
- features.bees-3th
parent: features.bees-2nh
created_at: '2026-02-12T08:20:33.721483'
updated_at: '2026-02-12T10:38:08.697173'
status: completed
bees_version: '1.1'
---

Review test coverage for delete_repo_agents (formerly cleanup_all_agents) after rename and implementation changes.

Check:
- Are existing tests in test_server.py lines 746-846 sufficient?
- Do tests cover subdirectory deletion behavior with new LIKE query?
- Do tests verify exact directory match vs subdirectory match?
- Are test assertions still valid after rename?

Add any missing test cases for:
- Subdirectory agent deletion
- Edge cases with similar directory paths
- Verification that agents outside repo tree are not deleted

Acceptance: Test coverage is complete for renamed function and subdirectory deletion behavior
