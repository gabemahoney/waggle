---
id: features.bees-z4j
type: t1
title: Refactor list_agents to use DB as source of truth instead of tmux
labels:
- enhancement
parent: features.bees-3za
children:
- features.bees-5bs
- features.bees-8t5
created_at: '2026-02-12T15:11:47.868635'
updated_at: '2026-02-12T15:23:18.787519'
status: completed
bees_version: '1.1'
---

Invert the current approach in `server.py` `list_agents`. Currently the flow is: enumerate all tmux sessions → look up each in DB → mark unmatched as "unknown". Change to: run `cleanup_dead_sessions()` (unchanged) → query DB for registered agents → enrich with tmux session info (e.g. session_path) for any that are still alive. This eliminates the "unknown" status entirely and ensures only actual Claude Code / OpenCode agents appear in the output. Update tests in `test_server.py` accordingly — remove or rework any tests that assert "unknown" status behavior.
