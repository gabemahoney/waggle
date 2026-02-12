---
id: features.bees-1qh
type: task
title: Remove unused HTTP config and minor dead code
down_dependencies:
- features.bees-9yk
parent: features.bees-c5g
children:
- features.bees-nmf
- features.bees-4py
- features.bees-vdq
- features.bees-925
- features.bees-grb
- features.bees-gj2
- features.bees-ox0
created_at: '2026-02-11T22:26:19.371640'
updated_at: '2026-02-11T22:52:34.732219'
priority: 0
status: completed
bees_version: '1.1'
---

**Context**: The Config class has HTTP host/port parsing for a removed HTTP server feature. Also minor dead code in server.py and resolve_repo_root.

**What Needs to Change**:
- Delete `http_host`, `http_port` parsing in `src/waggle/config.py:26-39`
- Delete `_validate_host()` method from config.py
- Remove `ipaddress` import from config.py
- Remove useless `except Exception: raise` in `server.py:50-51`
- Remove unused `source` variable in `resolve_repo_root`

**Why**: HTTP server was removed but config parsing remained. Clean exception handling.

**Success Criteria**:
- Config class no longer has http_host/http_port attributes
- No `ipaddress` import in config.py
- `poetry run pytest` passes
- `poetry run python -m waggle.server` starts without error
