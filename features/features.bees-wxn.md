---
id: features.bees-wxn
type: t3
title: Refactor list_agents to query DB first instead of enumerating tmux sessions
down_dependencies:
- features.bees-jzl
- features.bees-fcj
- features.bees-mur
parent: features.bees-5bs
created_at: '2026-02-12T15:15:38.747065'
updated_at: '2026-02-12T15:15:52.268236'
status: open
bees_version: '1.1'
---

**Context**: Currently list_agents enumerates all tmux sessions then matches against DB, showing "unknown" for non-agent sessions. Need to invert this to query DB first.

**Requirements**:
- Keep cleanup_dead_sessions() call at start (line 171)
- Replace tmux enumeration logic (lines 173-217) with DB query as primary source
- Query DB for all state entries and build list of registered agents
- For each DB entry, check if corresponding tmux session exists and enrich with session_path
- Remove "unknown" status entirely - only return DB-registered agents
- Maintain name and repo filtering functionality

**Files**: src/waggle/server.py lines 136-264

**Acceptance**: list_agents queries DB first, enriches with tmux data, returns only DB-registered agents, no "unknown" status in output
