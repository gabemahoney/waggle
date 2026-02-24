---
id: b.PUY
type: bee
title: send_command does not support "Chat about this" option in ask_user prompts
labels:
- bug
- send_command
- ask_user
parent: null
egg: null
created_at: '2026-02-24T10:10:05.388465'
status: worker
schema_version: 1.0.0
guid: PUYnHshsWoARhuiuS61MTq
---

## Bug

When `AskUserQuestion` renders a prompt in Claude Code's TUI, there is a special "Chat about this" element rendered **below** the numbered options list (visually separated). It is not part of the numbered sequence.

When `send_command` is called with the apparent number of "Chat about this" (e.g. `"6"`), it selects the numbered option at that index instead — it does not navigate to the special "Chat about this" UI element.

## Expected Behavior

`send_command` should be able to target and activate "Chat about this" when it is present in an `ask_user` prompt.

## Current Behavior

Sending the number corresponding to "Chat about this" selects a regular numbered option instead (e.g. the top option in the list, since the number wraps or maps incorrectly).

## Steps to Reproduce

1. Have an agent present an `ask_user` prompt with options
2. Note "Chat about this" rendered below the numbered list
3. Call `send_command` with the number shown next to "Chat about this"
4. Observe: a regular numbered option is selected instead

## Fix Ideas

- Detect presence of "Chat about this" in `prompt_data` and expose it as a special navigable option
- Support arrow-key navigation in `send_command` so callers can down-arrow to it and press Enter
- Or surface "Chat about this" as a dedicated parameter/flag in `send_command`
