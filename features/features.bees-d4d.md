---
id: features.bees-d4d
type: t3
title: Update test_list_agents_without_repo_filter_returns_all to only return DB-registered
  agents
down_dependencies:
- features.bees-pun
parent: features.bees-8t5
created_at: '2026-02-12T15:15:56.452340'
updated_at: '2026-02-12T15:21:24.308118'
status: completed
bees_version: '1.1'
---

Update test_list_agents_without_repo_filter_returns_all (around line 582 in test_server.py). Ensure test verifies that only DB-registered agents are returned, not all tmux sessions.

Context: The refactored list_agents queries DB first, then enriches with tmux data. Unregistered sessions should be excluded.

Files: test_server.py

Acceptance: Test verifies only DB-registered agents are returned, test passes
