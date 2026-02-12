---
id: features.bees-gj2
type: subtask
title: Review unit tests for this Task. See if you need to update, delete or add any.
up_dependencies:
- features.bees-nmf
down_dependencies:
- features.bees-ox0
parent: features.bees-1qh
created_at: '2026-02-11T22:27:14.153890'
updated_at: '2026-02-11T22:42:17.852891'
status: completed
bees_version: '1.1'
---

**Context**: Removing HTTP config fields - tests may reference http_host/http_port.

**What to do**:
- Search for tests that reference http_host, http_port, or _validate_host
- Remove or update tests that test removed functionality
- Ensure remaining config tests still work

**Acceptance**: No tests reference removed HTTP config, all remaining tests pass.
