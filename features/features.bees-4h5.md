---
id: features.bees-4h5
type: t3
title: Review unit tests for this Task. See if you need to update, delete or add any.
up_dependencies:
- features.bees-hub
down_dependencies:
- features.bees-2nq
parent: features.bees-3ym
created_at: '2026-02-12T10:52:17.315878'
updated_at: '2026-02-12T10:59:55.619914'
status: completed
bees_version: '1.1'
---

Review and update unit tests for the file:// URI parsing changes in get_client_repo_root().

Requirements:
- Check existing tests in test_server.py for get_client_repo_root()
- Add tests for:
  - Percent-encoded paths (spaces, special characters)
  - file://localhost/ variant handling
  - file:/// standard format
- Update any existing tests that may be affected by the implementation change
- Ensure edge cases are covered

Files: tests/test_server.py, src/waggle/server.py

Parent Task: features.bees-3ym

Acceptance: Test suite covers all URI parsing scenarios including percent-encoding and localhost variants
