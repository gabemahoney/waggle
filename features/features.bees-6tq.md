---
id: features.bees-6tq
type: subtask
title: Create pytest fixtures for common mock patterns
up_dependencies:
- features.bees-1as
down_dependencies:
- features.bees-31a
parent: features.bees-k6v
created_at: '2026-02-12T10:51:35.558324'
updated_at: '2026-02-12T11:04:20.417680'
status: completed
bees_version: '1.1'
---

**Context**: Need to extract repeated tmux + DB mocking into reusable fixtures based on identified patterns.

**What to do**:
- Create fixture for mocking tmux subprocess.run (with configurable return values)
- Create fixture for mocking database connection/cursor
- Create fixture for mocking cleanup_dead_sessions
- Create fixture for mocking context (AsyncMock with list_roots)
- Create fixture for tmp_path database setup
- Add fixtures to tests/test_server.py or conftest.py

**Files**: tests/test_server.py, tests/conftest.py (if needed)

**Acceptance**:
- All common mock patterns have corresponding fixtures
- Fixtures are parameterizable for different test scenarios
- Fixtures use @pytest.fixture decorator properly
