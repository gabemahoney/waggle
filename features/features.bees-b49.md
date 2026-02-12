---
id: features.bees-b49
type: t2
title: Update cleanup_all_agents to use new key format without namespace
parent: features.bees-28i
created_at: '2026-02-12T08:20:46.351422'
updated_at: '2026-02-12T09:22:52.185490'
status: completed
bees_version: '1.1'
---

Refactor `cleanup_all_agents()` in `src/waggle/server.py` to work with the new key format.

**Context**: Keys no longer contain namespace prefix. Instead, we filter by the `repo` column. The function should delete all entries where `repo` matches the resolved repo_root.

**Requirements**:
- Change DELETE query to filter by `repo` column instead of key prefix
- Old query: `DELETE FROM state WHERE key LIKE ?` with `f"{namespace}:%"`
- New query: `DELETE FROM state WHERE repo = ?` with `namespace` (which is actually repo_root)
- Keep variable name `namespace` for now (will be renamed in a different task)

**Files to Modify**:
- `src/waggle/server.py:cleanup_all_agents()` (lines 263-315)

**Key Change**:
```python
# OLD:
cursor.execute(
    "DELETE FROM state WHERE key LIKE ?",
    (f"{namespace}:%",)
)

# NEW:
cursor.execute(
    "DELETE FROM state WHERE repo = ?",
    (namespace,)
)
```

**Acceptance**:
- cleanup_all_agents deletes entries by repo column match
- Deletion count returned correctly
- No LIKE queries or namespace prefix patterns remain
