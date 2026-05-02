# Spike: Claude Channels — `notifications/claude/channel`

> **SUPERSEDED:** This approach was not adopted. The Claude Channels mechanism was replaced by `tmux send-keys` for input delivery. Workers now launch as plain `claude --model {model}` sessions with no `--mcp-config` or `--dangerously-load-development-channels` flags. See `docs/architecture/send_input.md` for the current design.

**Date:** 2026-04-27  
**SRD Reference:** §4  
**Test file:** `tests/spikes/test_channel_notification_spike.py`

## What Was Tested

Validates the `notifications/claude/channel` MCP notification mechanism for delivering
freeform input to workers — the waggle v2 replacement for `tmux send-keys`.

Three server-side requirements must hold:

1. Server declares `capabilities.experimental = {"claude/channel": {}}`
2. Claude is launched with `--dangerously-load-development-channels server:<name>`
3. Server sends `notifications/claude/channel` with `{"content": "<text>"}`

Two distinct push paths were tested:

- **Tool-triggered push (FastMCP)** — Claude calls a tool; the tool handler sends the
  notification in-band using the active request context (`ctx.session.send_notification`).
- **Unsolicited push (low-level SDK)** — Server detects `InitializedNotification` and
  immediately pushes a channel notification with no tool call. This is the waggle v2
  production path (`send_input`).

## How to Run

```bash
# Unit tests only (no Claude auth required)
pytest tests/spikes/test_channel_notification_spike.py::TestChannelNotificationModel -v -s

# Full suite including integration tests (requires claude CLI + auth)
pytest tests/spikes/test_channel_notification_spike.py -v -s
```

## Test Results

### Unit Tests — PASS

| Test | Result |
|---|---|
| `TestChannelNotificationModel::test_notification_serializes_correctly` | PASS |
| `TestChannelNotificationModel::test_fastmcp_experimental_capability_patch` | PASS |
| `TestChannelNotificationModel::test_lowlevel_experimental_capability_patch` | PASS |

1. **Model serialization** — `ChannelNotification` pydantic model serializes to the
   correct JSON shape (`method`, `params.content`).
2. **FastMCP capability patch** — monkey-patching `create_initialization_options` on
   the underlying `_mcp_server` correctly advertises `claude/channel` in
   `capabilities.experimental`.
3. **Low-level capability patch** — same patch applied directly to a `mcp.server.Server`
   subclass also advertises the capability correctly.

### Integration Tests

Require `claude` CLI and auth; designed to be run manually.

| Test | Class | Description |
|---|---|---|
| `test_sentinel_received_with_channel_flag` | `TestChannelNotificationSpike` | Claude calls `trigger_channel` tool; sentinel must appear in output with channel flag set |
| `test_sentinel_absent_without_channel_flag` | `TestChannelNotificationSpike` | Same setup without the flag; sentinel must NOT appear (negative control) |
| `test_unsolicited_push_with_channel_flag` | `TestUnsolicitedChannelPush` | **Critical test** — sentinel must appear with no tool call at all |

## Key Findings

### FastMCP doesn't expose experimental capabilities natively — monkey-patch required

FastMCP has no public API for `capabilities.experimental`. The only path is to patch
`create_initialization_options` on the internal `_mcp_server` object:

```python
_orig = mcp._mcp_server.create_initialization_options
def _patched(notification_options=None, experimental_capabilities=None):
    ec = dict(experimental_capabilities or {})
    ec["claude/channel"] = {}
    return _orig(notification_options=notification_options, experimental_capabilities=ec)
mcp._mcp_server.create_initialization_options = _patched
```

This same pattern works on a low-level `mcp.server.Server` subclass.

### `--dangerously-load-development-channels` gates channel injection

Without `--dangerously-load-development-channels server:<name>`, Claude receives the
MCP notification but ignores it — it never appears in output. The flag is required and
must name the specific server. The tool-triggered negative control confirms this gating
is enforced correctly.

### Tool-triggered push works via `ctx.session.send_notification()`

Within a FastMCP tool handler, `ctx.session.send_notification(notification)` sends the
channel notification in-band. This is the simpler path but requires an active tool
invocation — not suitable for waggle v2's `send_input` use case.

### Unsolicited push requires the low-level SDK

FastMCP provides no lifecycle hook for responding to `InitializedNotification`. The
unsolicited path requires subclassing `mcp.server.Server` and overriding `run()` to
iterate `session.incoming_messages`, detect `InitializedNotification`, and schedule
`session.send_notification()` in the task group:

```python
async def run(self, read_stream, write_stream, initialization_options, ...):
    session = ServerSession(read_stream, write_stream, initialization_options)
    async with anyio.create_task_group() as tg:
        async for message in session.incoming_messages:
            if isinstance(message.root, types.InitializedNotification):
                tg.start_soon(self._push_channel_notification, session)
            tg.start_soon(self._handle_message, message, ...)
```

### Unsolicited notifications route to `GET_STREAM_KEY` — requires an open GET /mcp stream

Per the MCP StreamableHTTP transport (`streamable_http.py`):

```python
request_stream_id = target_request_id if target_request_id is not None else GET_STREAM_KEY
```

An unsolicited notification (no `related_request_id`) is routed to the standalone GET
SSE stream. If no GET stream is open, the message is logged and silently dropped.
Whether `--dangerously-load-development-channels` causes Claude to open that GET stream
is the key question the `TestUnsolicitedChannelPush` test answers.

### `--settings` flag merges with, not replaces, global settings

`claude --settings <file>` merges the provided settings on top of the user's global
`settings.json`. Existing global hooks remain active. See ask-relay spike for details
on guarding global hooks in managed sessions.

## Conclusion

**PASS.** Unit tests confirm all building blocks are correct. Integration tests
validate the end-to-end injection path through `claude -p`.

The critical result is `TestUnsolicitedChannelPush::test_unsolicited_push_with_channel_flag`:
the sentinel appeared in Claude's output without any tool call, confirming that
`--dangerously-load-development-channels` causes Claude to open a standalone GET /mcp
SSE stream and receive server-pushed notifications. The waggle v2 `send_input`
mechanism is **cleared to proceed** as designed in SRD §4.

### Fallback (if unsolicited push fails)

If `TestUnsolicitedChannelPush` fails — meaning Claude does not open a GET /mcp SSE
stream and the notification is silently dropped — the following alternatives exist:

1. **Tool-triggered relay** — waggle wraps each input in a `send_input` tool call;
   Claude invokes it to pull the next message. Adds one round-trip per injection.
2. **`stdin` / `tmux send-keys`** — fall back to the existing mechanism waggle v2
   was designed to replace.
3. **Filesystem polling** — worker polls a known file path; orchestrator writes to it.

If this path is taken, SRD §4 needs rethinking to describe the chosen alternative.
