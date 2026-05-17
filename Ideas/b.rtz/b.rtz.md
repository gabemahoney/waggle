---
id: b.rtz
type: bee
title: Claude Spawn injects caller Claude Status ID for orphan detection
status: larva
created_at: '2026-05-16T22:18:53.588618'
schema_version: '0.1'
reference_materials: null
guid: rtz8czwaaiemzycdtnken4wwx2pm6k1n
---

## Idea

Claude Spawn should inject the caller's Claude Status ID as an env var into spawned Claude processes.

## Why

The Claude Status sweeper currently can't tell if a spawned Claude has been orphaned (i.e., its caller no longer exists). With the caller ID present in the spawned process's environment (and surfaced as a label in Claude Status), the sweeper can:

- Look up the caller's Claude Status entry
- If the caller is gone, mark the spawned worker as orphaned
- Reap the orphan as part of the normal sweep

## Notes

- Env var name TBD (e.g., `CLAUDE_SPAWN_CALLER_STATUS_ID`)
- The caller must already be registered in Claude Status for this to work; if not, fall back to no-orphan-tracking gracefully.
- Should also surface as a `claude_status_label` on the spawned worker so it's queryable.

## Related

- Plan Bee `b.nwq` (in flight) — spawn options + templates overhaul
