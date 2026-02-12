---
id: features.bees-nmf
type: subtask
title: Remove http_host/http_port parsing and _validate_host() from config.py
down_dependencies:
- features.bees-925
- features.bees-grb
- features.bees-gj2
parent: features.bees-1qh
created_at: '2026-02-11T22:26:49.766362'
updated_at: '2026-02-11T22:41:32.937629'
status: completed
bees_version: '1.1'
---

**Context**: The HTTP server feature was removed but config parsing code remains.

**What to do**:
- Delete `http_host`, `http_port` parsing in `src/waggle/config.py:26-39`
- Delete `_validate_host()` method from config.py
- Remove `ipaddress` import from config.py

**Acceptance**: Config class no longer has http_host/http_port attributes, no ipaddress import.
