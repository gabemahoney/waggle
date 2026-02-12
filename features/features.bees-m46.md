---
id: features.bees-m46
type: t2
title: Rename cleanup_all_agents function to delete_repo_agents
parent: features.bees-2nh
created_at: '2026-02-12T08:20:18.763048'
updated_at: '2026-02-12T10:24:41.532648'
status: completed
bees_version: '1.1'
---

Rename the function in src/waggle/server.py from cleanup_all_agents to delete_repo_agents.

Context: The name "cleanup_all_agents" is misleading since it doesn't delete ALL agents system-wide, but only agents for a specific repository.

Changes:
- Rename function definition at server.py:264
- Update @mcp.tool() decorator to use new name "waggle_delete_repo_agents"
- Update function docstring to reflect accurate behavior

Files affected:
- src/waggle/server.py

Acceptance: Function is renamed, decorator updated, docstring reflects new name and purpose
