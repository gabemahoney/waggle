---
id: features.bees-oee
type: t2
title: Update list_agents() docstring to reflect new behavior
parent: features.bees-3d5
created_at: '2026-02-11T23:39:54.645300'
updated_at: '2026-02-11T23:47:44.217413'
status: completed
bees_version: '1.1'
---

Context: The docstring currently says "Only returns agents in the current namespace" (line 126). This is no longer accurate after our changes.

What to Do:
- Update the docstring at lines 123-138 in `/Users/gmahoney/projects/waggle/src/waggle/server.py`
- Change "Only returns agents in the current namespace" to "Returns all agents system-wide with optional filtering by repository path"
- Add documentation for the new `repo` parameter in the Args section:
  - `repo: Optional filter to return only agents whose namespace contains this substring (case-insensitive)`
- Update the Returns section to document the new "namespace" field in agent objects:
  - Success: {"status": "success", "agents": [{"name": str, "session_id": str, "directory": str, "status": str, "namespace": str | None}, ...]}

Why: Documentation must accurately reflect the function's current behavior.

Acceptance Criteria:
- Docstring accurately describes system-wide agent listing
- repo parameter is documented in Args section
- namespace field is documented in Returns section
- Docstring follows same formatting style as before
