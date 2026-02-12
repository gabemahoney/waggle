---
id: features.bees-kn9
type: t1
title: Inline get_connection() into the connection() context manager
parent: features.bees-n6y
created_at: '2026-02-12T12:11:23.491593'
updated_at: '2026-02-12T12:23:04.615532'
priority: 0
status: completed
bees_version: '1.1'
---

## What

`database.py:48-64` defines `get_connection()` as a public function, but it's only called from the `connection()` context manager on line 87 in the same file. It wraps `sqlite3.connect()` and re-raises with a marginally better message. No production code calls it directly.

## How

1. Delete the `get_connection()` function from `database.py`
2. Replace the call in `connection()` with `conn = sqlite3.connect(db_path)` directly
3. Delete `tests/test_database.py::TestGetConnection` (the test class that tests `get_connection()` in isolation — lines ~121-155)
4. Remove `get_connection` from the import in `tests/test_database.py`
5. Run `poetry run pytest` to confirm nothing breaks

## Files
- `src/waggle/database.py`
- `tests/test_database.py`
