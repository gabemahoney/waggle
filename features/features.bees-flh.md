---
id: features.bees-flh
type: t3
title: Update test_list_agents_custom_states_with_unknown_status to verify only DB-registered
  agents appear
down_dependencies:
- features.bees-pun
parent: features.bees-8t5
created_at: '2026-02-12T15:15:53.259858'
updated_at: '2026-02-12T15:16:05.670441'
status: open
bees_version: '1.1'
---

Update test_list_agents_custom_states_with_unknown_status (around line 927 in test_server.py). Remove assertions about "unknown" status. Verify that only DB-registered agents appear in output.

Context: After refactoring, list_agents uses DB as source of truth. Sessions without DB entries should not appear at all.

Files: test_server.py

Acceptance: Test verifies only DB-registered agents appear, no "unknown" assertions, test passes
