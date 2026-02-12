---
id: features.bees-3th
type: t2
title: Fix delete_repo_agents to delete subdirectory agents
down_dependencies:
- features.bees-zfa
- features.bees-t7o
- features.bees-tb7
- features.bees-tgz
parent: features.bees-2nh
created_at: '2026-02-12T08:07:20.423097'
updated_at: '2026-02-12T10:28:37.032826'
status: completed
bees_version: '1.1'
---

After the namespace refactor (features.bees-28i), delete_repo_agents needs to delete agents running in the specified directory AND all subdirectories.

With the new schema using a separate 'repo' column, the implementation should be:

```python
cursor.execute(
    "DELETE FROM state WHERE repo = ? OR repo LIKE ?",
    (repo_path, f"{repo_path}/%")
)
```

This matches:
- Exact directory: `/Users/gmahoney/projects/waggle`
- All subdirectories: `/Users/gmahoney/projects/waggle/src`, `/Users/gmahoney/projects/waggle/tests`, etc.

Treats repo_path like a glob pattern - deletes agents in that directory AND all nested subdirectories.
