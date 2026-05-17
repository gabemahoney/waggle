---
id: b.fkb
type: bee
title: Rename Waggle → Claude Spawn
up_dependencies:
- b.hys
parent: null
children:
- t1.fkb.vx
- t1.fkb.tf
- t1.fkb.zr
- t1.fkb.y2
- t1.fkb.si
- t1.fkb.jg
- t1.fkb.xy
reference_materials:
- value: b.hys
  resolver: bees
created_at: '2026-05-16T13:12:05.541888'
status: finished
schema_version: '0.1'
guid: fkbjxa4djv2o8s24f6j1qhtx5vojipa8
---

# Plan: Rename Waggle → Claude Spawn

Implement the rename from `Waggle` to `Claude Spawn` end-to-end (repo, package, CLI, MCP server name, env vars, label keys, tmux session prefix, sting pattern, docs) and delete dead daemon-era code as a hard cutover with no compatibility shims.

Scope and rationale are defined in the parent Idea Bee `b.hys` (PRD: `t1.hys.e8`, SRD: `t1.hys.wp`). Decomposed into seven Epics, each of which leaves the codebase green; sequencing chains Epic 1 → Epic 2 → fan-out to Epics 3, 4, 5, 6 → Epic 7.
