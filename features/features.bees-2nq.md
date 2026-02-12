---
id: features.bees-2nq
type: t3
title: Run unit tests and fix failures
up_dependencies:
- features.bees-4h5
parent: features.bees-3ym
created_at: '2026-02-12T10:52:19.511421'
updated_at: '2026-02-12T11:00:29.068367'
status: completed
bees_version: '1.1'
---

Execute the full test suite and fix any failures that arise from the file:// URI handling changes.

Requirements:
- Run `poetry run pytest` to execute all tests
- Fix any test failures, even if they appear pre-existing
- Ensure 100% test pass rate
- Test with repo paths containing spaces to verify success criteria

Files: tests/test_server.py, src/waggle/server.py

Parent Task: features.bees-3ym

Success Criteria from parent:
- URI parsing handles percent-encoded characters correctly
- Both file:/// and file://localhost/ variants work
- Tests pass with repo paths containing spaces

Acceptance: All tests pass, including manual verification with space-containing paths
