---
id: features.bees-2nh
type: t1
title: Rename cleanup_all_agents to delete_repo_agents
up_dependencies:
- features.bees-28i
parent: features.bees-86c
children:
- features.bees-3th
- features.bees-m46
- features.bees-w51
- features.bees-zfa
- features.bees-t7o
- features.bees-tb7
- features.bees-tgz
created_at: '2026-02-12T07:57:59.019653'
updated_at: '2026-02-12T10:43:37.516377'
status: completed
bees_version: '1.1'
---

The name "cleanup_all_agents" is misleading - it doesn't delete ALL agents system-wide, it deletes agents for a specific repository.

After the namespace refactor (features.bees-28i), this function will query the new 'repo' column to filter which agents to delete.

Changes needed:
- Rename function from cleanup_all_agents to delete_repo_agents
- Update implementation to query WHERE repo = ? OR repo LIKE ? (for subdirectories)
- Update @mcp.tool() decorator
- Update function docstring
- Update any callers or references
- Update tests
