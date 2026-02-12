---
id: features.bees-86c
type: bee
title: Simplify namespace resolution and remove unused repo_root parameters
children:
- features.bees-gbf
- features.bees-rer
- features.bees-2nh
- features.bees-28i
created_at: '2026-02-12T07:57:37.885723'
updated_at: '2026-02-12T10:45:13.181274'
priority: 2
status: completed
bees_version: '1.1'
---

Currently we have two methods for capturing working directory:
1. pwd in bash hooks (used by agents when writing state)
2. MCP roots protocol + repo_root fallback (used by MCP tools)

The repo_root parameter in list_agents is dead code - it's resolved but never used. We should simplify the architecture to use pwd consistently and remove the unused parameters.

Goals:
- Remove repo_root from list_agents (it's dead code)
- Simplify namespace resolution to use pwd consistently
- Rename cleanup_all_agents to delete_repo_agents for clarity
