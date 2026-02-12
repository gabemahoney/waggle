---
id: features.bees-1as
type: subtask
title: Identify common mocking patterns in test_server.py
down_dependencies:
- features.bees-6tq
parent: features.bees-k6v
created_at: '2026-02-12T10:51:33.016980'
updated_at: '2026-02-12T11:04:03.353158'
status: completed
bees_version: '1.1'
---

**Context**: test_server.py has ~1193 lines with ~20 copies of the same tmux + DB mocking pattern. Need to understand what patterns repeat.

**What to do**:
- Read through test_server.py and identify repeating mock patterns
- Document which mocks are used repeatedly (tmux subprocess.run, DB connection, cleanup_dead_sessions, etc.)
- Identify what varies between test cases vs what stays constant
- List which test classes use which patterns

**Files**: tests/test_server.py

**Acceptance**: 
- Clear list of repeating mock patterns documented
- Understanding of what can be extracted to fixtures
