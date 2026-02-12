---
id: features.bees-lms
type: subtask
title: Update get_db_path() to use DEFAULT_DB_PATH constant
parent: features.bees-giv
created_at: '2026-02-12T10:51:56.432663'
updated_at: '2026-02-12T11:13:00.745944'
status: closed
bees_version: '1.1'
---

Context: get_db_path() function currently computes the default path inline (config.py:60).

Requirements:
- Replace inline `Path.home() / ".waggle" / "agent_state.db"` with `DEFAULT_DB_PATH` constant
- Ensure logic preserves existing behavior (fallback when config has no database_path)
- Update to: `db_path = str(DEFAULT_DB_PATH)`

Files: src/waggle/config.py:60

Acceptance: Function uses constant instead of computing path inline
