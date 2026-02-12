---
id: features.bees-vc5
type: t3
title: Add new test verifying sessions without DB entries are excluded from output
down_dependencies:
- features.bees-pun
parent: features.bees-8t5
created_at: '2026-02-12T15:15:58.521525'
updated_at: '2026-02-12T15:16:05.677242'
status: open
bees_version: '1.1'
---

Add a new test to test_server.py that explicitly verifies sessions without DB entries are excluded from list_agents output.

Test should:
- Create a tmux session that is NOT registered in DB
- Call list_agents
- Assert that the unregistered session does NOT appear in results
- Assert only DB-registered agents appear

Context: This is a positive test for the new behavior after refactoring.

Files: test_server.py

Acceptance: New test added and passing
