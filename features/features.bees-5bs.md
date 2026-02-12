---
id: features.bees-5bs
type: t2
title: Refactor list_agents to use DB as source of truth
parent: features.bees-z4j
children:
- features.bees-wxn
- features.bees-jzl
- features.bees-fcj
- features.bees-mur
- features.bees-c88
created_at: '2026-02-12T15:15:01.209503'
updated_at: '2026-02-12T15:15:58.112184'
status: open
bees_version: '1.1'
---

Currently `list_agents` enumerates all tmux sessions then matches them against the DB, marking unmatched sessions as "unknown". This pollutes output with non-agent tmux sessions. The new approach should query DB first, then enrich with tmux info.

Modify `list_agents` function in src/waggle/server.py:136-264:
- Keep `cleanup_dead_sessions()` call at start (line 171)
- Replace tmux enumeration logic with DB query as primary source
- For each DB entry, check if tmux session exists and enrich with session_path
- Remove "unknown" status entirely - only return DB-registered agents
- Update output structure to only include agents with DB entries

Success Criteria:
- `list_agents` returns only DB-registered agents
- No sessions with "unknown" status appear in output
- Session enrichment with tmux info (session_path) works for live sessions
- Name and repo filters still work correctly
- Dead sessions are cleaned up before querying
