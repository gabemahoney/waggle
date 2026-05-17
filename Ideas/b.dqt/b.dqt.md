---
id: b.dqt
type: bee
title: Spawn options and templates for Claude Spawn workers
up_dependencies:
- b.hys
down_dependencies:
- b.nwq
parent: null
children:
- t1.dqt.zb
- t1.dqt.da
reference_materials: null
created_at: '2026-05-16T12:59:11.242344'
status: finished
schema_version: '0.1'
guid: dqtha42xuqyjnjendf4w7mwk23616m7q
---

## Idea

Add spawn options + templates to Claude Spawn workers. Today `spawn_worker(model, repo, session_name?)` exposes only three knobs. Operators want more (CWD, instance_id, claude_home, claude_settings, permissions, env vars, status labels, CLI flags, thinking level, and more), and they want to bundle common configurations as **named templates** so an LLM can spawn a worker by saying `template="orchestrator"` instead of repeating a long options dict on every call.

## Why

The current three-knob signature is undersized for the things operators already want to configure per-spawn. Hand-passing the full options dict on every call is verbose, error-prone, and contrary to the "as little work as possible at the LLM boundary" principle. Templates let an operator tune a worker shape once and reference it by name forever.

## In scope

- Extending `spawn_worker` with a richer parameter set (PRD enumerates the full list and details).
- A spawn-templates config layer at `~/.claude-spawn/templates/` so common configurations can be saved and invoked by name.
- New MCP tools: `list_templates` (discovery) and `write_template` (programmatic authoring).
- New CLI subcommand: `claude-spawn write-template <name>` with interactive and flag-driven authoring modes.
- A spawn-readiness change: `spawn_worker` blocks until the worker registers itself with Claude Status, so callers can `send_input` / inspect state immediately on a successful return.
- Documentation updates (README + architecture docs).

## Out of scope

- Template inheritance / `extends` chains. v1 templates are flat single-file definitions.
- Template field-level editing via MCP. `write_template` writes the whole file (with an overwrite-safety story the PRD picks); partial patches / merges aren't supported.
- Live template reloading. Templates are read at spawn time.
- Template schema validation against a formal JSON Schema. Best-effort parse + clear error on malformed file.
- Migration from any prior spawn-options system (there isn't one).
