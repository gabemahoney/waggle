---
id: features.bees-bu4
type: t2
title: Implement case-insensitive namespace filtering when repo parameter provided
parent: features.bees-3d5
created_at: '2026-02-11T23:39:48.122938'
updated_at: '2026-02-11T23:47:25.912155'
status: completed
bees_version: '1.1'
---

Context: After sessions have namespace field populated, we need to filter the results based on the `repo` parameter if provided.

What to Do:
- Add filtering logic after session statuses are assigned (after line 221) in `/Users/gmahoney/projects/waggle/src/waggle/server.py`
- If `repo` parameter is not None:
  - Filter sessions list to only include sessions where the namespace contains the repo substring (case-insensitive)
  - Use `.lower()` for case-insensitive comparison
  - Handle None namespaces gracefully (exclude them from results when filtering)
- If `repo` parameter is None, return all sessions unfiltered

Why: Users need to filter agents by repository path to focus on specific projects.

Acceptance Criteria:
- `list_agents(repo="waggle")` returns only agents with "waggle" in namespace (case-insensitive)
- `list_agents(repo="WAGGLE")` returns same results (case-insensitive match)
- `list_agents()` without repo param returns all agents
- Sessions with None namespace are excluded when repo filtering is active
