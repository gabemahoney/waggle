---
id: features.bees-3za
type: bee
title: Filter list_agents to only show DB-registered sessions
labels:
- enhancement
children:
- features.bees-z4j
created_at: '2026-02-12T15:11:35.884545'
updated_at: '2026-02-12T15:11:47.870389'
status: open
bees_version: '1.1'
---

Currently `list_agents` queries all tmux sessions and marks any without a DB entry as "unknown". This pollutes the output with non-agent tmux sessions (personal shells, builds, etc.). Change `list_agents` to only return sessions that have a matching entry in the waggle state DB. Users who want to see all tmux sessions can run `tmux ls` directly.
