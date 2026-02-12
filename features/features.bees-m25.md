---
id: features.bees-m25
type: t2
title: Update list_agents to use new key format and query repo column
parent: features.bees-28i
created_at: '2026-02-12T08:20:37.587510'
updated_at: '2026-02-12T09:14:13.633359'
status: completed
bees_version: '1.1'
---

Refactor `list_agents()` in `src/waggle/server.py` to work with the new database schema.

**Context**: With the schema change, keys no longer contain namespace prefix. Agent location is now stored in the `repo` column. The composite key logic stays the same but namespace handling is removed.

**Requirements**:
- Update database query to SELECT key, repo, status, updated_at
- Remove namespace extraction from key parsing (no more `key.split(':', 1)`)
- New key format is just: `{name}+{session_id}+{created}`
- Build state_map with repo instead of namespace: `composite_key -> (repo, status)`
- Update session dict to include `repo` field instead of `namespace`
- Update `repo` parameter filter to match against session["repo"] instead of session["namespace"]

**Files to Modify**:
- `src/waggle/server.py:list_agents()` (lines 206-254)

**Key Changes**:
```python
# OLD: cursor.execute("SELECT key, value FROM state")
# NEW: cursor.execute("SELECT key, repo, status FROM state")

# OLD: namespace_part, composite_key = key.split(':', 1)
# NEW: composite_key = key  # No namespace prefix anymore

# OLD: state_map[composite_key] = (namespace_part, value)
# NEW: state_map[composite_key] = (repo, status)

# OLD: session["namespace"] = namespace_part
# NEW: session["repo"] = repo
```

**Acceptance**:
- list_agents returns sessions with `repo` field showing current working directory
- Repo filter works correctly
- No references to namespace remain in list_agents code
