---
id: features.bees-p5z
type: subtask
title: Run unit tests and fix failures
up_dependencies:
- features.bees-als
parent: features.bees-4xb
created_at: '2026-02-12T11:48:34.493897'
updated_at: '2026-02-12T12:13:07.102786'
status: completed
bees_version: '1.1'
---

Execute test suite after removing obsolete tests. Verify all remaining tests pass.

Command: pytest tests/test_server.py

Acceptance: All tests pass, no failures, no skipped tests referencing old 2-column schema
