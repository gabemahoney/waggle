"""Spike test: validate notifications/claude/channel injection mechanism.

This validates the core mechanism waggle v2 will use to deliver freeform input
to workers: the MCP server sends `notifications/claude/channel` and Claude Code
injects the content into the worker's context (instead of tmux send-keys).

Required setup on the server side:
  1. Server declares `capabilities.experimental = {"claude/channel": {}}`
  2. Claude is launched with `--dangerously-load-development-channels server:<name>`
  3. Server sends `notifications/claude/channel` with `{"content": "<text>"}`

Two test classes:

  TestChannelNotificationSpike — tool-triggered push (confirmed working)
    Claude calls trigger_channel → tool sends the notification → sentinel appears.
    This validates basic end-to-end channel injection.

  TestUnsolicitedChannelPush — truly unsolicited push (waggle v2 production path)
    Server detects InitializedNotification → immediately pushes channel notification
    without any tool call. Success requires Claude to open a standalone GET /mcp
    SSE stream (the MCP StreamableHTTP mechanism for server-push). Whether this
    works is the key question for Epic 3.

Run manually:
  pytest tests/spikes/test_channel_notification_spike.py -v -s
"""

import contextlib
import json
import socket
import subprocess
import threading
import time
from contextlib import asynccontextmanager
from typing import Any

import anyio
import pytest
import starlette.applications
import starlette.routing
import uvicorn
from fastmcp import Context, FastMCP
from mcp import types
from mcp.server import Server
from mcp.server.session import ServerSession
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.types import Notification

SENTINEL = "CHANNEL_SPIKE_SENTINEL_99"
SERVER_NAME = "test-channel-server"
CLAUDE_TIMEOUT = 90


# ---------------------------------------------------------------------------
# Shared: custom notification type
# ---------------------------------------------------------------------------


class ChannelNotification(Notification):
    """Typed wrapper for the `notifications/claude/channel` MCP notification."""

    method: str = "notifications/claude/channel"
    params: dict[str, Any]


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _find_free_port() -> int:
    with socket.socket() as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def _mcp_config(port: int) -> dict:
    return {
        "mcpServers": {
            SERVER_NAME: {
                "type": "http",
                "url": f"http://127.0.0.1:{port}/mcp",
            }
        }
    }


def _start_uvicorn(starlette_app, port: int) -> uvicorn.Server:
    """Start a uvicorn server in a daemon thread; return the Server object."""
    uv_config = uvicorn.Config(
        starlette_app, host="127.0.0.1", port=port, log_level="warning"
    )
    uv_server = uvicorn.Server(uv_config)
    thread = threading.Thread(target=uv_server.run, daemon=True)
    thread.start()

    deadline = time.monotonic() + 10.0
    while not uv_server.started:
        if time.monotonic() > deadline:
            raise RuntimeError(f"MCP test server did not start within 10 s on port {port}")
        time.sleep(0.05)

    return uv_server


# ---------------------------------------------------------------------------
# Tool-triggered server (FastMCP)
# ---------------------------------------------------------------------------


def _build_fastmcp_app() -> FastMCP:
    """Return a FastMCP app for the tool-triggered channel spike.

    Modifications vs. a plain FastMCP app:
    1. Monkey-patches `create_initialization_options` to advertise
       `experimental.claude/channel`.
    2. Registers `trigger_channel` tool that sends the notification when called.
    """
    mcp = FastMCP(SERVER_NAME)

    _orig_create = mcp._mcp_server.create_initialization_options

    def _patched_create(notification_options=None, experimental_capabilities=None):
        ec = dict(experimental_capabilities or {})
        ec["claude/channel"] = {}
        return _orig_create(
            notification_options=notification_options,
            experimental_capabilities=ec,
        )

    mcp._mcp_server.create_initialization_options = _patched_create

    @mcp.tool()
    async def trigger_channel(ctx: Context) -> str:
        """Send notifications/claude/channel with the spike sentinel.

        Uses the active request context (ctx.session) to send the notification
        in-band with the tool call. This validates the basic injection path but
        requires an active request — see TestUnsolicitedChannelPush for the
        waggle production path (truly unsolicited push).
        """
        notification = ChannelNotification(
            method="notifications/claude/channel",
            params={"content": SENTINEL},
        )
        await ctx.session.send_notification(notification)
        return "channel notification sent"

    return mcp


@pytest.fixture
def channel_server(tmp_path):
    """FastMCP tool-triggered server. Yields (port, mcp_config_path)."""
    port = _find_free_port()
    uv_server = _start_uvicorn(_build_fastmcp_app().http_app(), port)

    config_path = tmp_path / "mcp.json"
    config_path.write_text(json.dumps(_mcp_config(port)))

    yield port, config_path

    uv_server.should_exit = True
    thread.join(timeout=5.0)


# ---------------------------------------------------------------------------
# Unsolicited server (low-level mcp.server.Server)
# ---------------------------------------------------------------------------


class _UnsolicitedChannelServer(Server):
    """Low-level MCP server that pushes a channel notification unsolicited.

    Overrides `run()` to hook into the message loop. When it sees the client's
    `notifications/initialized` (completion of the MCP handshake), it schedules
    `_push_channel_notification(session)` in the existing anyio task group.

    The notification is sent to the transport's write stream, which routes it to
    the GET_STREAM_KEY (the standalone SSE stream). For Claude to receive it,
    Claude must have opened a GET /mcp SSE connection — which happens when
    `--dangerously-load-development-channels` is active. If Claude does not open
    that stream, the message is dropped by the transport and the test fails,
    which is itself a valid spike result (see TestUnsolicitedChannelPush docstring).
    """

    def __init__(self, name: str) -> None:
        super().__init__(name)
        self._push_done = False

        @self.list_tools()
        async def list_tools() -> list[types.Tool]:
            return [
                types.Tool(
                    name="noop",
                    description="Placeholder tool (unsolicited test needs no tool call).",
                    inputSchema={"type": "object", "properties": {}},
                )
            ]

        @self.call_tool()
        async def call_tool(
            name: str, arguments: dict
        ) -> list[types.TextContent]:
            return [types.TextContent(type="text", text="noop")]

    async def run(
        self,
        read_stream,
        write_stream,
        initialization_options,
        raise_exceptions: bool = False,
        stateless: bool = False,
    ) -> None:
        from contextlib import AsyncExitStack

        async with AsyncExitStack() as stack:
            lifespan_context = await stack.enter_async_context(self.lifespan(self))
            session = await stack.enter_async_context(
                ServerSession(
                    read_stream,
                    write_stream,
                    initialization_options,
                    stateless=stateless,
                )
            )

            async with anyio.create_task_group() as tg:
                async for message in session.incoming_messages:
                    # Detect InitializedNotification → schedule unsolicited push
                    if (
                        not self._push_done
                        and isinstance(message, types.ClientNotification)
                        and isinstance(message.root, types.InitializedNotification)
                    ):
                        self._push_done = True
                        tg.start_soon(self._push_channel_notification, session)

                    tg.start_soon(
                        self._handle_message,
                        message,
                        session,
                        lifespan_context,
                        raise_exceptions,
                    )

    async def _push_channel_notification(self, session: ServerSession) -> None:
        """Push notifications/claude/channel with sentinel after init settles."""
        await anyio.sleep(0.3)  # Brief pause so the handshake fully completes
        notification = ChannelNotification(
            method="notifications/claude/channel",
            params={"content": SENTINEL},
        )
        await session.send_notification(notification)


def _build_unsolicited_starlette_app() -> starlette.applications.Starlette:
    """Build a Starlette ASGI app backed by _UnsolicitedChannelServer."""
    server = _UnsolicitedChannelServer(SERVER_NAME)

    # Patch experimental capability onto the low-level server
    _orig = server.create_initialization_options

    def _patched(notification_options=None, experimental_capabilities=None):
        ec = dict(experimental_capabilities or {})
        ec["claude/channel"] = {}
        return _orig(
            notification_options=notification_options,
            experimental_capabilities=ec,
        )

    server.create_initialization_options = _patched

    session_manager = StreamableHTTPSessionManager(
        app=server,
        json_response=False,
        stateless=False,
    )

    @asynccontextmanager
    async def lifespan(app):
        async with session_manager.run():
            yield

    return starlette.applications.Starlette(
        routes=[
            starlette.routing.Route(
                "/mcp",
                endpoint=session_manager.handle_request,
                methods=["GET", "POST", "DELETE"],
            )
        ],
        lifespan=lifespan,
    )


@pytest.fixture
def unsolicited_channel_server(tmp_path):
    """Low-level unsolicited-push server. Yields (port, mcp_config_path)."""
    port = _find_free_port()
    uv_server = _start_uvicorn(_build_unsolicited_starlette_app(), port)

    config_path = tmp_path / "mcp.json"
    config_path.write_text(json.dumps(_mcp_config(port)))

    yield port, config_path

    uv_server.should_exit = True
    thread.join(timeout=5.0)


# ---------------------------------------------------------------------------
# Unit tests — no claude CLI required
# ---------------------------------------------------------------------------


class TestChannelNotificationModel:
    """Validate building blocks before running the full integration."""

    def test_notification_serializes_correctly(self):
        n = ChannelNotification(
            method="notifications/claude/channel",
            params={"content": SENTINEL},
        )
        dumped = n.model_dump(by_alias=True, mode="json", exclude_none=True)
        assert dumped["method"] == "notifications/claude/channel"
        assert dumped["params"]["content"] == SENTINEL

    def test_fastmcp_experimental_capability_patch(self):
        """Monkey-patched FastMCP server advertises claude/channel capability."""
        mcp = _build_fastmcp_app()
        opts = mcp._mcp_server.create_initialization_options()
        assert opts.capabilities.experimental is not None
        assert "claude/channel" in opts.capabilities.experimental

    def test_lowlevel_experimental_capability_patch(self):
        """Low-level server also advertises claude/channel capability."""
        server = _UnsolicitedChannelServer(SERVER_NAME)
        _orig = server.create_initialization_options

        def _patched(notification_options=None, experimental_capabilities=None):
            ec = dict(experimental_capabilities or {})
            ec["claude/channel"] = {}
            return _orig(
                notification_options=notification_options,
                experimental_capabilities=ec,
            )

        server.create_initialization_options = _patched
        opts = server.create_initialization_options()
        assert opts.capabilities.experimental is not None
        assert "claude/channel" in opts.capabilities.experimental


# ---------------------------------------------------------------------------
# Integration tests — require claude CLI + auth
# ---------------------------------------------------------------------------


class TestChannelNotificationSpike:
    """Tool-triggered channel push: validates basic injection end-to-end."""

    def test_sentinel_received_with_channel_flag(self, channel_server):
        """With --dangerously-load-development-channels, sentinel appears in output.

        Flow: Claude calls trigger_channel → tool sends notifications/claude/channel
        → if the flag causes Claude to inject channel content, SENTINEL appears.
        """
        _, config_path = channel_server

        prompt = (
            "Call the trigger_channel tool. "
            "After calling it, look for any channel message you received from the server. "
            "Reply with ONLY this exact format: 'Channel received: <message>' "
            "where <message> is the exact content of the channel notification. "
            "No other text."
        )

        result = subprocess.run(
            [
                "claude",
                "-p", prompt,
                "--mcp-config", str(config_path),
                "--dangerously-load-development-channels", f"server:{SERVER_NAME}",
                "--dangerously-skip-permissions",
            ],
            capture_output=True,
            text=True,
            timeout=CLAUDE_TIMEOUT,
        )

        assert result.returncode == 0, (
            f"claude exited with code {result.returncode}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )
        assert SENTINEL in result.stdout, (
            f"Sentinel '{SENTINEL}' not found in Claude's output — "
            "notifications/claude/channel injection did not work.\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )

    def test_sentinel_absent_without_channel_flag(self, channel_server):
        """Without --dangerously-load-development-channels, sentinel must NOT appear.

        Claude calls trigger_channel and receives the tool result ("channel notification
        sent"). The server also sends notifications/claude/channel with SENTINEL, but
        Claude should ignore it without the flag — so SENTINEL must not appear in output.
        """
        _, config_path = channel_server

        prompt = (
            "Call the trigger_channel tool. "
            "Report what the tool returned. "
            "Reply with ONLY: 'Tool returned: <result>' — no other text."
        )

        result = subprocess.run(
            [
                "claude",
                "-p", prompt,
                "--mcp-config", str(config_path),
                # No --dangerously-load-development-channels
                "--dangerously-skip-permissions",
            ],
            capture_output=True,
            text=True,
            timeout=CLAUDE_TIMEOUT,
        )

        assert result.returncode == 0, (
            f"claude exited with code {result.returncode}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )
        assert SENTINEL not in result.stdout, (
            f"Sentinel appeared WITHOUT the channel flag — "
            "notifications/claude/channel is not properly gated.\n"
            f"stdout:\n{result.stdout}"
        )


class TestUnsolicitedChannelPush:
    """Truly unsolicited push: server sends notification after connect, no tool call.

    This is the waggle v2 production path. The server detects InitializedNotification
    and immediately pushes notifications/claude/channel. For Claude to receive it,
    Claude must open a standalone GET /mcp SSE stream (the MCP StreamableHTTP
    mechanism for server-initiated push).

    Per the MCP StreamableHTTP transport code (streamable_http.py line ~891):
        request_stream_id = target_request_id if target_request_id is not None else GET_STREAM_KEY

    An unsolicited notification (no related_request_id) is routed to GET_STREAM_KEY.
    If no GET stream is open, the message is logged and dropped. Whether
    --dangerously-load-development-channels causes Claude to open a GET stream is
    the key question this test answers.

    OUTCOMES:
      PASS → Claude opens a GET stream; unsolicited push works; Epic 3 can proceed.
      FAIL → Claude does not open a GET stream; unsolicited push is silently dropped;
             waggle v2 will need a different injection mechanism before Epic 3.
    """

    def test_unsolicited_push_with_channel_flag(self, unsolicited_channel_server):
        """Sentinel appears without any tool call when the channel flag is set.

        The prompt deliberately does NOT ask Claude to call any tool. If SENTINEL
        appears, it came purely from the unsolicited channel notification.
        """
        _, config_path = unsolicited_channel_server

        prompt = (
            "Do NOT call any tools. "
            "Wait briefly, then report any channel message you received from the server. "
            "Reply with ONLY: 'Channel received: <message>' if a message arrived, "
            "or 'No channel message received' if nothing arrived. "
            "No other text."
        )

        result = subprocess.run(
            [
                "claude",
                "-p", prompt,
                "--mcp-config", str(config_path),
                "--dangerously-load-development-channels", f"server:{SERVER_NAME}",
                "--dangerously-skip-permissions",
            ],
            capture_output=True,
            text=True,
            timeout=CLAUDE_TIMEOUT,
        )

        assert result.returncode == 0, (
            f"claude exited with code {result.returncode}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )
        assert SENTINEL in result.stdout, (
            f"Sentinel '{SENTINEL}' NOT found — unsolicited push did not reach Claude.\n"
            f"This means Claude does not open a standalone GET /mcp SSE stream for\n"
            f"server-push, even with --dangerously-load-development-channels.\n"
            f"waggle v2's send_input will need a different injection approach.\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )
