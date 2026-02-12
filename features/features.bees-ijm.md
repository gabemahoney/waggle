---
id: features.bees-ijm
type: t2
title: Remove repo_root parameter from list_agents function
down_dependencies:
- features.bees-6zr
- features.bees-xvs
- features.bees-to8
parent: features.bees-gbf
created_at: '2026-02-12T08:20:07.618413'
updated_at: '2026-02-12T10:03:55.729290'
status: completed
bees_version: '1.1'
---

Remove the unused repo_root parameter from the list_agents function in src/waggle/server.py.

**Context**: The repo_root parameter is resolved at line 156 into a namespace variable but never used in the function. The actual repository filtering happens via the 'repo' parameter using substring matching on the namespace field.

**Changes**:
- Remove repo_root parameter from function signature (line 121)
- Remove the resolve_repo_root call at line 156 that creates the unused namespace variable
- Update the function docstring to remove repo_root parameter documentation (line 142)

**Files**: src/waggle/server.py:118-260

**Acceptance**: Function signature and docstring no longer reference repo_root parameter, resolve_repo_root call is removed
