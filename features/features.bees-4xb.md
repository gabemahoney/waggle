---
id: features.bees-4xb
type: task
title: Remove 3 obsolete E2E tests from test_server.py
parent: features.bees-02t
children:
- features.bees-als
- features.bees-p5z
created_at: '2026-02-12T11:47:20.549002'
updated_at: '2026-02-12T12:16:21.547820'
priority: 0
status: completed
bees_version: '1.1'
---

Context: Three skipped tests at lines 1040, 1150, and 1328 assert against a 2-column schema that no longer exists. The hook now uses a 4-column schema.

What Needs to Change:
- Delete the test at line 1040
- Delete the test at line 1150
- Delete the test at line 1328

Files: tests/test_server.py

Bee: features.bees-02t

Success Criteria:
- All three obsolete tests are removed
- Remaining tests pass
- No skipped tests referencing the old 2-column schema
