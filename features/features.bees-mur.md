---
id: features.bees-mur
type: t3
title: Review unit tests for this Task. See if you need to update, delete or add any.
up_dependencies:
- features.bees-wxn
down_dependencies:
- features.bees-c88
parent: features.bees-5bs
created_at: '2026-02-12T15:15:52.256826'
updated_at: '2026-02-12T15:15:58.113879'
status: open
bees_version: '1.1'
---

**Context**: Task refactored list_agents in server.py. Tests in test_server.py may assert "unknown" status behavior that no longer exists.

**Requirements**: 
- Review tests in test_server.py related to list_agents
- Remove or rework tests asserting "unknown" status behavior
- Add tests for new DB-first query approach
- Test that only DB-registered agents appear in output
- Test name and repo filtering still works

**Files**: test_server.py

**Acceptance**: All list_agents tests reflect new DB-first behavior, no tests expect "unknown" status
