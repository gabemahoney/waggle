---
id: features.bees-hub
type: t3
title: Replace naive string slicing with urllib.parse for file:// URIs
down_dependencies:
- features.bees-3ue
- features.bees-2ku
- features.bees-4h5
parent: features.bees-3ym
created_at: '2026-02-12T10:52:11.078357'
updated_at: '2026-02-12T10:59:09.168443'
status: completed
bees_version: '1.1'
---

Context: Lines 40-43 in server.py use naive string slicing `root_uri_str[7:]` to strip the `file://` prefix. This doesn't handle percent-encoded characters or `file://localhost/` variants.

Requirements:
- Import urllib.parse at top of file
- Replace string slicing logic (lines 40-43) with:
  - urllib.parse.urlparse() to parse the URI
  - urllib.parse.unquote() to decode percent-encoded characters
  - Handle both `file:///path` and `file://localhost/path` variants

Files: src/waggle/server.py:40-43

Acceptance:
- URIs with percent-encoded characters (e.g., `file:///path%20with%20spaces`) decode correctly
- Both `file:///` and `file://localhost/` variants work
- Code is cleaner and more robust than string slicing

Parent Task: features.bees-3ym
