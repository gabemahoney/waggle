---
id: features.bees-3ym
type: t2
title: Fix file:// URI handling in server.py
parent: features.bees-y9l
children:
- features.bees-hub
- features.bees-3ue
- features.bees-2ku
- features.bees-4h5
- features.bees-2nq
created_at: '2026-02-12T10:50:45.973526'
updated_at: '2026-02-12T11:00:30.188453'
priority: 0
status: completed
bees_version: '1.1'
---

Context: The current file:// URI handling uses naive string slicing which doesn't handle percent-encoded characters (like spaces) or file://localhost/ variants properly.

What Needs to Change:
- Replace string slicing in server.py:40-43 with urllib.parse.urlparse() + urllib.parse.unquote()
- Handle file://localhost/ variants correctly
- Handle percent-encoded characters in paths (e.g., %20 for spaces)

Files: src/waggle/server.py

Bee: features.bees-y9l

Success Criteria:
- URI parsing handles percent-encoded characters correctly
- Both file:/// and file://localhost/ variants work
- Tests pass with repo paths containing spaces
