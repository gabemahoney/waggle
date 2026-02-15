---
id: features.bees-mlj
type: t1
title: Add send_keys and read_pane MCP tools
labels:
- mcp-tools
- orchestration
up_dependencies:
- features.bees-sya
parent: features.bees-rao
created_at: '2026-02-14T20:59:42.423215'
updated_at: '2026-02-14T20:59:50.080071'
status: open
bees_version: '1.1'
---

## Goal

Add two new MCP tools to `server.py` that allow an orchestrator agent to interact with waggle-registered agents through their tmux panes.

## Agent Resolution Helper

`resolve_agent_pane(name, session_id=None)` — shared by both tools:
1. Query DB for keys matching `{name}+%`
2. Validate exactly one match (or use `session_id` to disambiguate)
3. Use `tmux.find_session()` + `tmux.get_active_pane()` to get pane
4. Return `(agent_info_dict, pane)` or `(error_dict, None)`
5. Security boundary — only DB-registered agents can be targeted
6. All libtmux calls wrapped with `asyncio.to_thread()`

## send_keys tool

```
send_keys(name: str, text: str, enter: bool = True, session_id: str = None) -> dict
```
- Resolves agent → pane, sends text via `tmux.send_keys()`
- Returns `{"status": "success", "agent": name, "text_sent": text, "enter": bool}`

## read_pane tool

```
read_pane(name: str, start: int = None, end: int = None, session_id: str = None) -> dict
```
- Resolves agent → pane, captures content via `tmux.capture_pane()`
- Returns `{"status": "success", "agent": name, "lines": [...], "line_count": int}`
- start/end control scrollback range (default = visible screen only)

## Tests

Add tests to `test_server.py` — mock `waggle.tmux` module functions, test success/error/disambiguation paths.
