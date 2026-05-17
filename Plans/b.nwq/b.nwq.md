---
id: b.nwq
type: bee
title: Spawn options and templates for Claude Spawn workers
up_dependencies:
- b.dqt
parent: null
children:
- t1.nwq.qq
- t1.nwq.d2
- t1.nwq.uu
- t1.nwq.c4
- t1.nwq.vv
- t1.nwq.sn
reference_materials:
- value: b.dqt
  resolver: bees
created_at: '2026-05-16T17:40:43.566482'
status: finished
schema_version: '0.1'
guid: nwq1i69ryrxjyaxyfrn1ffncxzfpgrre
---

## Goal

Replace `spawn_worker`'s three-knob `(model, repo, session_name)` signature with the v1 12-option surface; add a TOML-based spawn-templates layer under `~/.claude-spawn/templates/` (loadable by name, authorable via MCP and CLI); and make `spawn_worker` block until Claude Status registration so callers can use the returned `tmux_session_name` immediately.

## Scope

Six Epics, each a vertical capability slice that leaves the codebase green:

1. New `spawn_worker` option surface and Claude Code launch composition (incl. `permissions`/`claude_settings` overlay synthesis).
2. Spawn-readiness blocking with timeout cleanup and worker-exited-early detection.
3. TOML template loader and `template=<name>` resolution with merge semantics.
4. `list_templates` MCP tool with malformed-template `skipped[]` channel.
5. `write_template` MCP tool with name safety, schema validation, and `force` overwrite.
6. `claude-spawn write-template` CLI subcommand with flag-driven and interactive modes.

Out of scope (per PRD/SRD): template inheritance, field-level patches, live reload, JSON Schema validation, builtin templates, migration tooling, `initial_prompt`, per-call readiness-timeout override.

## Source documents

- PRD: `t1.dqt.zb`
- SRD: `t1.dqt.da`
- Idea Bee: `b.dqt`
- Rename prerequisite (already shipped): Plan Bee `b.fkb`
