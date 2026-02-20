---
id: b.W4r
type: bee
title: 'send_command: Ctrl+C clears ask_user/check_permission dialogs before sending
  option'
parent: null
egg: null
created_at: '2026-02-20T08:31:48.259296'
status: worker
schema_version: 1.0.0
---

## Bug

`send_command` always calls `clear_pane_input` (which sends `Ctrl+C`) before delivering the command, regardless of agent state. When the agent is in `ask_user` or `check_permission` state, `Ctrl+C` dismisses the dialog entirely instead of clearing partial text input. The option number is then delivered to the now-idle agent as a free-form message.

## Observed behavior

1. Agent shows `ask_user` prompt with numbered options
2. `send_command("5")` is called
3. `clear_pane_input` fires `Ctrl+C` → dialog dismissed, Claude Code logs "User declined to answer questions"
4. `"5"` arrives at the idle prompt as a new user message
5. Agent responds conversationally to "5" instead of selecting the option

## Root cause

`tmux.py:291` — `_clear_pane_input_sync` unconditionally sends `C-c`:
```python
pane.send_keys("C-c", enter=False)
```

`server.py` Step 7 calls `clear_pane_input` before every `send_keys_to_pane`, with no state check.

## Fix

Skip `clear_pane_input` when `agent_state` is `ask_user` or `check_permission`. These states have no partial text input to clear — `Ctrl+C` only harms them.
