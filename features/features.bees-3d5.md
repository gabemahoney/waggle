---
id: features.bees-3d5
type: t1
title: Update list_agents() with namespace filtering and output
parent: features.bees-0je
children:
- features.bees-zd8
- features.bees-7st
- features.bees-jln
- features.bees-bu4
- features.bees-oee
- features.bees-m3k
- features.bees-6hg
- features.bees-wto
- features.bees-3ve
created_at: '2026-02-11T23:38:47.171502'
updated_at: '2026-02-12T07:44:18.222033'
priority: 0
status: completed
bees_version: '1.1'
---

Context: Currently `list_agents()` only shows agents in the current directory. Users need to see all agents system-wide with optional filtering by repo path.

What Needs to Change:
- Modify `list_agents()` in `/Users/gmahoney/projects/waggle/src/waggle/server.py` (lines 123-235)
- Remove namespace filter from database query (line 197-199): change to `SELECT key, value FROM state`
- Add `repo: Optional[str] = None` parameter
- Extract namespace from state keys and add to session objects
- Filter sessions by namespace substring (case-insensitive) when repo param provided
- Update docstring to reflect new behavior

Why: Users running multiple projects need visibility into all active agents and ability to filter by project path.

Success Criteria:
- `list_agents()` returns agents from all directories
- `list_agents(repo="waggle")` filters to only agents with "waggle" in namespace path (case-insensitive)
- Output includes `namespace` field showing what repo the agent reported
- Docstring accurately describes new behavior
- Existing tests pass, new tests validate filtering

Files: /Users/gmahoney/projects/waggle/src/waggle/server.py
Bee: features.bees-0je
