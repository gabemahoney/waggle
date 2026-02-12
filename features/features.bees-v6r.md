---
id: features.bees-v6r
type: t3
title: Remove test_list_agents_returns_sessions_with_unknown_status test
down_dependencies:
- features.bees-pun
parent: features.bees-8t5
created_at: '2026-02-12T15:15:50.090440'
updated_at: '2026-02-12T15:21:22.667243'
status: completed
bees_version: '1.1'
---

Remove test_list_agents_returns_sessions_with_unknown_status (around line 367 in test_server.py). This test asserts that sessions without DB entries show "unknown" status. After refactoring, these sessions should not appear at all.

Context: Parent task refactors list_agents to use DB as source of truth, eliminating "unknown" status entirely.

Files: test_server.py

Acceptance: Test is removed, remaining tests pass
