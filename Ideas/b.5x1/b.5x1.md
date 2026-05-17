---
id: b.5x1
type: bee
title: 'Claude Status: rename crashed→missing, retain entries, capture session_id for resume'
parent: null
reference_materials: null
created_at: '2026-05-16T22:21:09.271853'
status: larva
schema_version: '0.1'
guid: 5x1tiaz9deanx5b5guxmb6bg5vr54xh4
---

## Idea

Four related changes to Claude Status (in support of full worker resume + configurable orphan cleanup):

### 1. Rename status `crashed` → `missing` (retain entries by default)

Today "crashed" entries are treated as terminal. Rename to `missing` to reflect that the process is unreachable but the entry has lingering value (resurrectable). Don't auto-delete a missing entry on detection; retention is governed by the new sweeper config (item 4).

### 2. Capture the Claude session_id in Claude Status

Claude Slack Channel Bots already captures the Claude CLI session id. Claude Status should do the same. Then Claude Spawn can:

- Read the session_id from the Claude Status entry of a `missing` worker
- Invoke `claude --resume <session_id>` to resurrect the ended session
- Pick up where it left off without losing context

### 3. Capture the resolved launch spec on the instance row (reuse the template format)

Resume needs more than `claude --resume <session_id>` — it needs the same launch context the worker started with: cwd, model, claude_args, extra_env, synthesized settings, labels, template ref, all of the b.nwq 12-option surface. Without this, resurrect can't faithfully reproduce permissions, env, model, or tooling.

**Reuse the template format** (`b.nwq`'s `claude_spawn.templates` module). The post-resolution launch is exactly "the template that was effectively in use after all merges and per-call overrides". Same allowed-keys schema, same validator (`templates._validate`), same value types. Two storage locations:

- TOML files under `~/.claude-spawn/templates/` — operator-authored, named, reusable
- JSON blob on Claude Status `instances` row — auto-captured at spawn, immutable, per-instance

On resume, hydrate the blob back through the same launch composition path Spawn already uses for templates. No new schema, no new validation, no drift.

Schema impact: single `launch_spec` JSON column on `instances`. Snapshot the resolved option-map at spawn time.

### 4. Configurable inactivity-based reap of missing instances

Add a sweeper config knob — e.g., `missing_reap_after_days` (default **30**) — that controls how long a `missing` instance is retained before the sweeper deletes its row.

Mechanics:

- Use the existing `instances.last_seen_at` column (already indexed) as the activity timestamp.
- On each sweep, an entry with `status = 'missing'` AND `now() - last_seen_at > missing_reap_after_days` is reaped (DELETE).
- Threshold is configurable via the same per-user/per-system config layering that already exists for `idle_timeout_seconds` (per b.zcd config resolution). Negative or zero disables reap (keep missing entries forever).
- Default 30 days is generous enough that an operator-driven resurrect is the norm; the sweeper is the safety net for forgotten orphans.

Together with item 1: `missing` entries are not lost on detection (resurrectable for up to N days); item 4 bounds the table from growing forever.

## Why

- Today, when a spawned Claude crashes / its tmux pane dies / it gets evicted, the work is lost — operator has to start over.
- With session_id + launch-spec capture + resume, we can revive a missing worker on demand and continue the in-flight task with the same context, permissions, env, and tooling.
- Renaming to `missing` clarifies that the entry is a candidate for resurrection, not a tombstone.
- The configurable reap (default 30d) prevents the table from accumulating dead entries forever while preserving the resurrection window for active work.
- Reusing the template format means no new schema to maintain, and the validator already exists.

## Notes

- Reference how CSCB extracts session_id from Claude CLI output for the pattern.
- Sweeper behavior changes: detect-and-mark-missing is decoupled from reap; reap is gated by `now() - last_seen_at > missing_reap_after_days`.
- Consider a `resurrect` Claude Spawn MCP tool that takes a Claude Status worker_id, looks up its session_id + launch_spec, and re-spawns with `--resume` plus the captured launch spec.
- Session transcript files already live at `~/.claude/projects/<cwd-encoded>/<session-uuid>.jsonl` and persist by default — no separate file persistence work needed; `claude --resume <id>` reads them from the canonical path.
- Config plumbing: reuse the per-user / per-system / env-var layering pattern from `idle_timeout_seconds` (b.zcd) so operators set this the same way they set existing knobs.

## Related

- `b.rtz` — caller-orphan tracking (this idea complements it: an orphaned worker could be resurrected if its caller comes back, OR reaped after the configured inactivity window).
- `b.evz` (finished) — pass synthesized settings inline via `--settings` JSON string. The resolved settings land in the launch_spec blob directly (no file-path round-trip).
- Plan Bee `b.nwq` (finished) — spawn options + templates; defines the 12-option surface AND the template schema/validator that the launch_spec reuses.
- Bee `b.zcd` — established the config-resolution layering pattern (per-user / per-system / env-var) that `missing_reap_after_days` reuses.
