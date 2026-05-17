---
id: b.evz
type: bee
title: Pass synthesized settings inline via --settings JSON string (drop tempfile)
parent: null
reference_materials: null
created_at: '2026-05-17T08:13:20.398911'
status: finished
schema_version: '0.1'
guid: evzptmxq22sofpkgqxbe2d8fgj8ifqud
---

## Idea

Replace Claude Spawn's tempfile-based settings synthesis with inline JSON passed to `claude --settings <json-string>`.

## Why

Today `spawn.py:_resolve_settings_path` synthesizes the merged settings (`permissions` + optional caller `claude_settings` overlay) by writing to `tempfile.NamedTemporaryFile(prefix='claude-spawn-settings-', delete=False)`. Nothing ever unlinks these — every `spawn_worker` call with `permissions` leaks one `/tmp/claude-spawn-settings-*.json` file (deferred review items C4 + T4 from `b.nwq`).

**Tested 2026-05-17: `claude --help` documents `--settings <file-or-json>` — it accepts EITHER a path OR an inline JSON string.** Verified working:
- `claude --settings '{}' --version` → ok
- `claude --settings '{"permissions":{"allow":["Bash(echo)"]}}' --version` → ok

(Tried `<()` process substitution, `/dev/stdin`, `/proc/self/fd/N` — all rejected with "Settings file not found" because claude `statSync`s the path.)

So we don't need a file at all. The synthesized merged-settings dict can be `json.dumps()`'d and handed to claude directly. Zero disk, zero cleanup, no lifecycle to manage.

## Scope

- `spawn.py:_resolve_settings_path` — change the two `NamedTemporaryFile` branches (permissions-only, permissions+claude_settings-merge) to return a JSON string instead of a path.
- Launch composition — when the resolved settings is a string, pass `--settings <json>`; when caller passed `claude_settings` standalone (no `permissions` to merge), pass the path through unchanged (no synthesis needed in that case anyway).
- Update tests: `TestSettingsOverlay` no longer needs to assert a tempfile is written.
- Update arch doc + README "settings stack" section.

## Out of scope

- Caller's `claude_settings` file behavior is unchanged; we still read + merge it when both are present.
- Inline JSON length limit: claude CLI / OS argv max (~128KB on Linux). Settings dicts are tiny; not a concern.

## Related

- Plan Bee `b.nwq` (shipped) — origin of the tempfile mechanism
- Bee `b.rtz` — caller-orphan tracking
- Bee `b.5x1` — Claude Status crashed→missing + session_id capture (this idea makes the per-worker-run-dir discussion moot; lifecycle ownership of the settings file is no longer a problem)
