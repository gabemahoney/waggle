---
id: features.bees-rer
type: t1
title: Keep roots protocol + repo_root in cleanup function (no changes needed)
parent: features.bees-86c
created_at: '2026-02-12T07:57:52.752171'
updated_at: '2026-02-12T07:59:00.552722'
status: cancelled
bees_version: '1.1'
---

This epic is actually unnecessary. The cleanup_all_agents function correctly uses MCP roots protocol with repo_root fallback because it's called from an external context to target a specific repository.

This is different from list_agents where repo_root is dead code - cleanup actually USES the resolved namespace to delete entries.

The only change needed is the rename (tracked in features.bees-2nh).
