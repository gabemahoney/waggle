---
id: features.bees-ur5
type: t2
title: 'Migrate database schema: remove namespace from key, add repo column'
down_dependencies:
- features.bees-gzb
- features.bees-aar
- features.bees-rnv
parent: features.bees-28i
created_at: '2026-02-12T08:20:25.940303'
updated_at: '2026-02-12T08:28:11.273465'
status: completed
bees_version: '1.1'
---

Update the database schema in `src/waggle/database.py` to reflect the new architecture:

**Context**: Current schema embeds namespace in the composite key format `{namespace}:{name}+{session_id}+{created}`, causing orphaned entries when agents change directories. New architecture separates session identity from repo location.

**Requirements**:
- Remove namespace from PRIMARY KEY format
- New key format: `{name}+{session_id}+{created}` (session identity only)
- Add `repo` column (TEXT NOT NULL) to store current working directory
- Add `updated_at` column (TIMESTAMP) to track last update time
- Preserve existing `status` column (TEXT NOT NULL)

**Files to Modify**:
- `src/waggle/database.py`: Update `init_schema()` function with new CREATE TABLE statement

**New Schema**:
```sql
CREATE TABLE IF NOT EXISTS state (
    key TEXT PRIMARY KEY,      -- {name}+{session_id}+{created}
    repo TEXT NOT NULL,         -- current working directory (from pwd)
    status TEXT NOT NULL,       -- agent state (working, waiting, etc)
    updated_at TIMESTAMP        -- last update time
)
```

**Migration Strategy**:
- Use CREATE TABLE IF NOT EXISTS to handle new installations
- Existing installations will need manual migration (document separately)
- Schema change is backwards incompatible but acceptable for early stage project

**Acceptance**: 
- `init_schema()` creates table with new schema
- All four columns present: key, repo, status, updated_at
- Tests confirm schema matches specification
