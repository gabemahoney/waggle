---
id: features.bees-wto
type: t2
title: Review unit tests for this Task. See if you need to update, delete or add any.
up_dependencies:
- features.bees-zd8
down_dependencies:
- features.bees-3ve
parent: features.bees-3d5
created_at: '2026-02-11T23:40:18.377727'
updated_at: '2026-02-12T07:43:41.510002'
status: completed
bees_version: '1.1'
---

Context: We've modified `list_agents()` with new parameters and behavior. Tests need to validate the changes.

What to Do:
- Find existing tests for `list_agents()` in the test suite
- Update existing tests that may assume namespace filtering behavior
- Add new test cases for:
  - System-wide agent listing (no repo filter)
  - Repository filtering (case-insensitive substring match)
  - Namespace field in output (present when state exists, None otherwise)
  - Edge cases: None namespace handling, empty repo filter, no matching repos
- Use mocking for tmux and database interactions as appropriate
- Ensure tests cover all success criteria from parent Task

Parent Task: features.bees-3d5
Files: /Users/gmahoney/projects/waggle/src/waggle/server.py (list_agents function)

Acceptance Criteria:
- Tests validate system-wide listing works
- Tests validate repo filtering (case-insensitive)
- Tests validate namespace field appears in output
- Tests validate edge cases (None namespace, no matches, etc.)
- All new tests pass
