---
id: features.bees-gbf
type: t1
title: Remove repo_root parameter from list_agents
up_dependencies:
- features.bees-28i
parent: features.bees-86c
children:
- features.bees-ijm
- features.bees-3rb
- features.bees-6zr
- features.bees-xvs
- features.bees-to8
- features.bees-sm0
created_at: '2026-02-12T07:57:45.577180'
updated_at: '2026-02-12T10:14:40.109662'
status: completed
bees_version: '1.1'
---

The repo_root parameter in list_agents is dead code - it's resolved at line 156 but never used. The actual filtering happens via the 'repo' parameter using substring matching.

After the namespace refactor (features.bees-28i), list_agents will query agents from the database using the new 'repo' column instead of parsing namespace from composite keys.

Changes needed:
- Remove repo_root parameter from list_agents function signature
- Remove resolve_repo_root call that creates unused namespace variable
- Update filtering logic to query WHERE repo LIKE ? using the repo column
- Update function docstring
- Update tests if any reference repo_root
