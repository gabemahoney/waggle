---
id: features.bees-tgz
type: t2
title: Run unit tests and fix failures
up_dependencies:
- features.bees-3th
parent: features.bees-2nh
created_at: '2026-02-12T08:20:35.616930'
updated_at: '2026-02-12T10:40:40.258124'
status: completed
bees_version: '1.1'
---

Execute test suite after completing all Epic changes. Fix any failures.

Run:
```bash
poetry run pytest tests/test_server.py::TestCleanupAllAgents -v
```

Or full test suite:
```bash
poetry run pytest
```

Ensure 100% pass rate for all tests, including pre-existing tests.

Acceptance: All unit tests pass without failures
