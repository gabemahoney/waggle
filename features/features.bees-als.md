---
id: features.bees-als
type: subtask
title: Delete 3 obsolete skipped tests from test_server.py
down_dependencies:
- features.bees-p5z
parent: features.bees-4xb
created_at: '2026-02-12T11:48:26.138798'
updated_at: '2026-02-12T12:12:53.680685'
status: completed
bees_version: '1.1'
---

Remove three skipped tests that assert against a 2-column schema that no longer exists:
- Delete test at line 1040
- Delete test at line 1150  
- Delete test at line 1328

File: tests/test_server.py

Context: These tests were skipped waiting for hook update to 4-column schema. That update is complete, so tests are obsolete.

Acceptance: All three tests removed, no skipped tests referencing old 2-column schema remain
