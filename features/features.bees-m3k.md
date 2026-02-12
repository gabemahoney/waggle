---
id: features.bees-m3k
type: t2
title: View README and see if it needs to be changed based on changes done in this
  Task
up_dependencies:
- features.bees-zd8
parent: features.bees-3d5
created_at: '2026-02-11T23:40:04.255263'
updated_at: '2026-02-11T23:47:58.389701'
status: completed
bees_version: '1.1'
---

Context: We've modified `list_agents()` to support system-wide agent listing with optional repository filtering and namespace output.

What to Do:
- Read the README.md file
- Check if `list_agents()` or `waggle list` command is documented
- If documented, update to reflect:
  - System-wide listing (not just current directory)
  - New `repo` parameter for filtering by repository path
  - New `namespace` field in output
- Add usage examples if appropriate:
  - `waggle list` - shows all agents
  - `waggle list --repo waggle` - shows only agents in waggle repo

Why: Users need accurate documentation to understand how to use the new filtering capabilities.

Parent Task: features.bees-3d5

Acceptance Criteria:
- README accurately reflects new list_agents() behavior if the command is documented
- Examples show new filtering capability if examples are present
- No outdated information about "current directory only" limitation remains
