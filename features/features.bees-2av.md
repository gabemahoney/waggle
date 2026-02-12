---
id: features.bees-2av
type: subtask
title: Define DEFAULT_DB_PATH constant in config.py
down_dependencies:
- features.bees-uxa
- features.bees-f3j
- features.bees-6co
parent: features.bees-giv
created_at: '2026-02-12T10:51:54.075998'
updated_at: '2026-02-12T11:12:52.937849'
status: closed
bees_version: '1.1'
---

Context: Default database path `~/.waggle/agent_state.db` is currently duplicated in 3 locations.

Requirements:
- Add module-level constant at top of src/waggle/config.py (after imports):
  ```python
  DEFAULT_DB_PATH = Path.home() / ".waggle" / "agent_state.db"
  ```
- Add comment above constant explaining it's shared with hooks/set_state.sh:15
- Document that both locations must be updated if path changes

Files: src/waggle/config.py

Acceptance: Constant defined and documented at module level
