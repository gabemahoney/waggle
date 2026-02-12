---
id: features.bees-2jc
type: t2
title: Update hooks/set_state.sh to use new key format and write repo column
parent: features.bees-28i
created_at: '2026-02-12T08:21:16.060621'
updated_at: '2026-02-12T09:27:05.277872'
status: completed
bees_version: '1.1'
---

Refactor the bash hook script to write state using the new database schema.

**Context**: Bash hooks are called by agents to write their state. Currently writes key in format `{namespace}:{name}+{session_id}+{created}` with status in `value` column. Need to change to new format with separate `repo` column.

**Requirements**:
- Remove namespace from key format
- New key format: `{name}+{session_id}+{created}` (no namespace prefix)
- Update schema creation to match new format (4 columns: key, repo, status, updated_at)
- Change INSERT statement to write to `repo` and `status` columns instead of `value`
- Set `repo` column to pwd output (current working directory)
- Set `updated_at` to CURRENT_TIMESTAMP
- Remove `value` column references

**Files to Modify**:
- `hooks/set_state.sh` (entire file)

**Key Changes**:
```bash
# OLD: KEY="${NAMESPACE}:${NAME}+${SESSION_ID}+${CREATED}"
# NEW: KEY="${NAME}+${SESSION_ID}+${CREATED}"

# OLD schema:
# CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT);

# NEW schema:
CREATE TABLE IF NOT EXISTS state (
    key TEXT PRIMARY KEY,
    repo TEXT NOT NULL,
    status TEXT NOT NULL,
    updated_at TIMESTAMP
);

# OLD insert:
# INSERT OR REPLACE INTO state (key, value) VALUES ('$SAFE_KEY', '$SAFE_STATE');

# NEW insert:
INSERT OR REPLACE INTO state (key, repo, status, updated_at)
VALUES ('$SAFE_KEY', '$NAMESPACE', '$SAFE_STATE', CURRENT_TIMESTAMP);
```

**Note**: Variable NAMESPACE is still used but now represents repo path, not namespace prefix. Will be renamed in different task.

**Acceptance**:
- Hook writes state with new key format (no namespace prefix)
- Hook writes repo column with current pwd
- Hook writes status column with provided state
- Hook sets updated_at to current timestamp
- Tests confirm correct database entries after hook execution
