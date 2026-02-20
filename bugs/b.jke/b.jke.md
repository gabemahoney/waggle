---
id: b.jke
type: bee
title: Idle Claude Code prompt misclassified as ask_user, blocking send_command
labels:
- bug
- state-parser
- send_command
parent: null
egg: null
created_at: '2026-02-20T08:23:40.067399'
status: worker
schema_version: 1.0.0
---

## Summary

`send_command` errors with "could not parse options from ask_user prompt" when the agent is at the idle prompt. The state parser misclassifies the Claude Code idle input box as `ask_user`.

## Root Cause

Two bugs in `src/waggle/state_parser.py`:

**Bug 1 (line 34)** — `ask_user` check triggers on any content containing both `❯` (U+276F) and `───` (U+2500×3). The Claude Code idle prompt has both — the `❯` input cursor and the `───` border lines around it — but no numbered options. The parser returns `ask_user` before checking for options.

**Bug 2 (line 62)** — `_is_done` regex is `^>\s*$` (matches ASCII `>`), but the real Claude Code idle prompt ends with `❯` (U+276F). So the idle state never reaches `done` — it's caught by `ask_user` first (Bug 1), and would fall through to `unknown` if Bug 1 were fixed.

## Repro

1. Spawn agent: `spawn_agent` on any repo
2. Wait for it to reach idle state
3. Call `read_pane` — returns `agent_state: "ask_user"` with empty options
4. Call `send_command` with any command — returns error "could not parse options from ask_user prompt"

## Fix

**`src/waggle/state_parser.py`**

Fix 1 — only return `ask_user` when options are actually parsed:
```python
if "\u276f" in content and "\u2500\u2500\u2500" in content:
    data = _parse_ask_user(content)
    if data["options"]:
        return "ask_user", data
    # fall through — idle prompt has ❯ and ─── but no options
```

Fix 2 — match `❯` as a valid idle prompt char in `_is_done`:
```python
return bool(re.match(r"^[>❯]\s*$", stripped))
```

**Tests** — add to `tests/test_state_parser.py`:
- Idle Claude Code prompt (with `❯` input box and `───` borders, no options) classifies as `done`
- Idle prompt does NOT classify as `ask_user`

**New fixture** — `tests/fixtures/pane_snapshots/idle.txt` with real idle prompt snapshot.
