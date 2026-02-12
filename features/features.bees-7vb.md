---
id: features.bees-7vb
type: bee
title: Eliminate duplicated schema definitions via shared schema.sql and conformance
  test
children:
- features.bees-3wj
created_at: '2026-02-12T12:05:33.888636'
updated_at: '2026-02-12T12:45:07.988405'
priority: 2
status: completed
bees_version: '1.1'
---

## Problem

The `CREATE TABLE IF NOT EXISTS state` DDL is duplicated across two languages:

| Location | File | Role |
|---|---|---|
| Python server startup | `src/waggle/database.py:35-42` | Authoritative schema init on server start |
| Bash hook | `hooks/set_state.sh:79-84` | Defensive schema init (ensures table exists even if server hasn't started) |
| Tests | 7 places across `test_server.py` and `test_hooks.py` | Hardcoded DDL instead of using `init_schema()` |

If someone adds/removes/renames a column in `database.py`, the hook will silently write to the old schema. There is no automated check that the two definitions match.

The `INSERT OR REPLACE` statement in `set_state.sh:85-86` must also stay in sync with the column list.

## Solution

Create a single source-of-truth `schema.sql` file inside the Python package. Have `database.py` read from it instead of inline DDL. Keep the hook's inline DDL as an operational fallback (it must work even if the server hasn't run yet), but add a conformance test that fails if the hook's schema drifts from `schema.sql`.

### Approach: No runtime changes, development-time enforcement

- **No install steps or operational complexity** — the hook continues to work exactly as it does today
- **Drift is caught during development** — a unit test parses both `schema.sql` and `set_state.sh`, extracts column definitions, and asserts they match
- **Tests that hardcode DDL** are updated to use `init_schema()` where possible

## Execution Steps

### Step 1: Create `src/waggle/schema.sql`
Create the file with the canonical DDL extracted from `database.py`:
```sql
CREATE TABLE IF NOT EXISTS state (
    key TEXT PRIMARY KEY,
    repo TEXT NOT NULL,
    status TEXT NOT NULL,
    updated_at TIMESTAMP
);
```

### Step 2: Modify `src/waggle/database.py`
Change `init_schema()` to read DDL from `schema.sql` via `Path(__file__).parent / "schema.sql"` instead of the inline string. The function signature and behavior remain identical.

### Step 3: Add source-of-truth comment to `hooks/set_state.sh`
Above the inline `CREATE TABLE` block (line ~79), add:
```bash
# SCHEMA SOURCE OF TRUTH: src/waggle/schema.sql — keep in sync
```
This makes it clear where to look when changing the schema.

### Step 4: Create `tests/test_schema_conformance.py`
Write a conformance test that:
1. Parses `src/waggle/schema.sql` to extract column names, types, and constraints
2. Reads `hooks/set_state.sh` and extracts its `CREATE TABLE` statement
3. Asserts the hook's column names, types, and constraints match `schema.sql`
4. Extracts the `INSERT OR REPLACE` column list from the hook and asserts it references the same columns in the same order as `schema.sql`

The parsing can be simple regex/string matching — these are small, well-structured SQL statements, not arbitrary queries.

### Step 5: Fix hardcoded DDL in tests
Replace the 2 non-skipped hardcoded `CREATE TABLE` calls in `tests/test_hooks.py` (lines 458, 680) with `from waggle.database import init_schema; init_schema(db_path)`. The 5 instances in skipped E2E tests (which reference the old 2-column schema) are dead code and should be left alone or deleted separately.

### Step 6: Run tests
`poetry run pytest` — verify all 136+ tests pass, including the new conformance test.

## What This Catches

- Adding a column to `schema.sql` without updating `set_state.sh` → test fails
- Removing a column from `schema.sql` without updating `set_state.sh` → test fails
- Renaming a column → test fails
- Changing column types or constraints → test fails
- Reordering columns in the INSERT without matching the schema → test fails

## Files Affected

- `src/waggle/schema.sql` (new)
- `src/waggle/database.py` (modified — read DDL from file)
- `hooks/set_state.sh` (modified — comment only)
- `tests/test_schema_conformance.py` (new)
- `tests/test_hooks.py` (modified — replace 2 hardcoded DDL with `init_schema()`)
