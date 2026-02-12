---
id: features.bees-9yk
type: task
title: Remove dead Config class and load_config function
up_dependencies:
- features.bees-muc
- features.bees-1qh
- features.bees-a4i
parent: features.bees-c5g
children:
- features.bees-zjt
- features.bees-qwn
- features.bees-5pi
- features.bees-vz2
- features.bees-3v2
created_at: '2026-02-11T22:52:34.720883'
updated_at: '2026-02-11T22:55:32.577775'
priority: 1
status: completed
bees_version: '1.1'
---

**Context**: Code review discovered that the `Config` class and `load_config()` function in config.py are never imported or used anywhere in the codebase. Also found unused `os` import.

**What Needs to Change**:
- Delete `Config` class from config.py:13-32
- Delete `load_config()` function from config.py:35-45
- Remove unused `import os` from config.py:8
- Verify only `get_config()` and `get_db_path()` are used (confirmed via grep)

**Why**: Dead code cleanup - these functions were likely made obsolete when the code was refactored to use `get_db_path()` directly.

**Success Criteria**:
- Config class, load_config(), and unused os import removed from config.py
- Only `get_config()` and `get_db_path()` remain
- `poetry run pytest` passes
- No imports of Config or load_config elsewhere
