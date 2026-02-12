---
id: features.bees-giv
type: task
title: Extract DB path default constant
parent: features.bees-y9l
children:
- features.bees-2av
- features.bees-lms
- features.bees-uxa
- features.bees-f3j
- features.bees-6co
- features.bees-plw
created_at: '2026-02-12T10:50:50.273923'
updated_at: '2026-02-12T11:14:31.198223'
priority: 0
status: closed
bees_version: '1.1'
---

Context: Default path `~/.waggle/agent_state.db` is computed in 3 places: config.py:44, config.py:138, and set_state.sh:15.

What Needs to Change:
- Extract to module-level constant DEFAULT_DB_PATH in config.py
- Update all 3 locations to use the constant
- Document the coupling with bash script

Files: src/waggle/config.py, hooks/set_state.sh

Bee: features.bees-y9l

Success Criteria:
- Module-level constant defined
- All 3 locations updated
- Tests pass
