---
id: features.bees-jln
type: t2
title: Extract namespace from state keys and add to session objects
parent: features.bees-3d5
created_at: '2026-02-11T23:39:41.884349'
updated_at: '2026-02-11T23:47:15.501674'
status: completed
bees_version: '1.1'
---

Context: State keys have format `{namespace}:name+session_id+session_created`. We need to extract the namespace portion and include it in the session objects returned to users.

What to Do:
- Modify the state_map building logic around lines 206-214 in `/Users/gmahoney/projects/waggle/src/waggle/server.py`
- Change state_map from `composite_key -> status` to `composite_key -> (namespace, status)`
- When parsing state entries, extract both namespace and composite_key from the key
- Update the session status assignment logic (lines 217-221) to also set `session["namespace"]` from the state_map
- If no state entry exists for a session, set `session["namespace"] = None`

Why: Users need to see which repository/namespace each agent belongs to when viewing all agents system-wide.

Acceptance Criteria:
- Each session object includes a "namespace" field
- Namespace is extracted correctly from state keys (before the `:` separator)
- Sessions without state entries have namespace set to None
- Existing status assignment still works correctly
