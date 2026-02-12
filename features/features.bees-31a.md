---
id: features.bees-31a
type: subtask
title: Refactor test classes to use new fixtures
up_dependencies:
- features.bees-6tq
down_dependencies:
- features.bees-njf
parent: features.bees-k6v
created_at: '2026-02-12T10:51:39.441648'
updated_at: '2026-02-12T11:09:11.832548'
status: completed
bees_version: '1.1'
---

**Context**: Replace all repeated mock patterns with new fixture usage throughout test_server.py.

**What to do**:
- Go through each test class systematically
- Replace inline mock setup with fixture usage
- Update test method signatures to accept fixtures
- Remove redundant mock code
- Ensure test behavior remains identical

**Files**: tests/test_server.py

**Acceptance**:
- All test classes use fixtures instead of inline mocks
- No duplicate mock setup code remains
- File size reduced significantly (target ~600 lines from ~1193)
