---
id: features.bees-rnv
type: t2
title: Review unit tests for this Epic. See if you need to update, delete or add any.
up_dependencies:
- features.bees-ur5
down_dependencies:
- features.bees-t64
parent: features.bees-28i
created_at: '2026-02-12T08:21:53.184292'
updated_at: '2026-02-12T09:37:19.338018'
status: completed
bees_version: '1.1'
---

Review and update unit tests to cover the new database schema and refactored code.

**Context**: Database schema changed from namespace-prefixed keys to session identity keys with separate repo column. Multiple functions refactored in server.py and hooks updated. Need to ensure test coverage for new behavior.

**Requirements**:
- Review existing tests in tests/ directory (test_database.py, test_server.py, test_hooks.py)
- Identify tests that use old key format or schema assumptions
- Update tests to use new key format and schema
- Add tests for new repo column behavior
- Add tests for removed orphan cleanup logic (verify it's actually removed)
- Ensure tests cover: schema creation, list_agents, cleanup_all_agents, cleanup_dead_sessions, set_state hook

**Files to Review**:
- tests/test_database.py
- tests/test_server.py
- tests/test_hooks.py
- Any other test files that interact with the database

**Test Areas**:
- Schema initialization with 4 columns (key, repo, status, updated_at)
- Key format without namespace prefix
- list_agents returns repo field correctly
- cleanup_all_agents filters by repo column
- cleanup_dead_sessions only removes dead sessions (no duplicate removal)
- set_state hook writes repo and status correctly

**Acceptance**:
- All tests updated to match new schema
- New tests added for repo column functionality
- No tests reference old namespace-prefixed key format
- Test coverage maintained or improved
