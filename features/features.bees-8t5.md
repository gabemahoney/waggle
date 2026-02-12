---
id: features.bees-8t5
type: t2
title: Update list_agents tests to remove unknown status behavior
parent: features.bees-z4j
children:
- features.bees-v6r
- features.bees-flh
- features.bees-d4d
- features.bees-vc5
- features.bees-pun
created_at: '2026-02-12T15:15:07.553353'
updated_at: '2026-02-12T15:23:18.083994'
status: completed
bees_version: '1.1'
---

Current tests in test_server.py assert that sessions without DB entries show "unknown" status. After refactoring, these sessions should not appear at all.

Changes needed:
- Remove or update test_list_agents_returns_sessions_with_unknown_status (line 367)
- Update test_list_agents_custom_states_with_unknown_status (line 927) to verify only DB-registered agents appear
- Update test_list_agents_without_repo_filter_returns_all (line 582) - should only return DB-registered agents
- Add new test verifying sessions without DB entries are excluded from output
- Verify all other tests still pass with new behavior

Success Criteria:
- No tests assert "unknown" status exists
- Tests verify sessions without DB entries are excluded
- All name/repo filtering tests still pass
- Cleanup integration tests still pass
- Custom state tests still pass
