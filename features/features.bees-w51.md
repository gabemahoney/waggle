---
id: features.bees-w51
type: t2
title: Update all references to cleanup_all_agents in test file
parent: features.bees-2nh
created_at: '2026-02-12T08:20:23.335175'
updated_at: '2026-02-12T10:26:41.086316'
status: completed
bees_version: '1.1'
---

Update all references in tests/test_server.py to use new function name delete_repo_agents.

Context: After renaming cleanup_all_agents to delete_repo_agents, need to update test file references.

Changes needed in tests/test_server.py:
- Line 20: Update variable assignment from cleanup_all_agents to delete_repo_agents
- Line 746: Update test class/function docstring
- Lines 750, 761, 771, 782, 795, 806, 816, 824, 834, 846: Update test names and function calls

Files affected:
- tests/test_server.py

Acceptance: All references to cleanup_all_agents are renamed to delete_repo_agents in test file
