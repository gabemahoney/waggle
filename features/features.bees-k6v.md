---
id: features.bees-k6v
type: task
title: Reduce test duplication in test_server.py
parent: features.bees-y9l
children:
- features.bees-1as
- features.bees-6tq
- features.bees-31a
- features.bees-njf
- features.bees-usr
created_at: '2026-02-12T10:50:47.794654'
updated_at: '2026-02-12T11:10:05.717522'
priority: 0
status: completed
bees_version: '1.1'
---

Context: test_server.py has ~1193 lines with ~20 copies of the same tmux + DB mocking pattern.

What Needs to Change:
- Extract common mock setup into pytest fixtures
- Replace repeated mock patterns throughout test file
- Target: reduce file size by roughly 50%

Files: tests/test_server.py

Bee: features.bees-y9l

Success Criteria:
- Common mocking patterns extracted to fixtures
- File size reduced significantly (target ~600 lines)
- All tests still pass
