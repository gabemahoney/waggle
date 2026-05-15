"""Waggle stdio MCP server — the new stateless MCP surface.

Exposes two tools over stdio transport (SR-1.1):
  - spawn_worker
  - list_spawned_workers

The existing HTTP/TCP server (waggle.server) is left untouched.
This module contains no module-level side effects; import is inert.
The server is launched only when ``run()`` is called (from ``waggle mcp``).

SR-7.1 error wrapping: every tool body is wrapped in a try/except that
translates unexpected exceptions into an operation-failed dict so the LLM
always receives a structured response rather than a Python traceback.
"""

from __future__ import annotations

from fastmcp import FastMCP

from waggle import spawn

mcp = FastMCP("waggle-stdio")


def _err(operation: str, exc: Exception) -> dict:
    """Translate an unexpected exception into a SR-7.1 operation-failed dict."""
    return {
        "ok": False,
        "operation": operation,
        "err_name": "ErrUnexpected",
        "err_description": str(exc),
    }


@mcp.tool()
async def spawn_worker(
    model: str,
    repo: str,
    session_name: str | None = None,
) -> dict:
    """Spawn a new Claude worker in a tmux session.

    Args:
        model: Claude model name (e.g. "claude-sonnet-4-5").
        repo: Absolute path to the working repository.
        session_name: Optional tmux session name.
            Defaults to ``waggle-<8-char instance prefix>``.

    Returns:
        ``{"instance_id": str, "session_name": str}`` on success or
        an SR-7.1 operation-failed dict on failure.
    """
    import asyncio

    try:
        return await asyncio.to_thread(spawn.spawn_worker_impl, model, repo, session_name)
    except Exception as exc:
        return _err("spawn_worker", exc)


@mcp.tool()
async def send_input(session_name: str, text: str) -> dict:
    """Send text verbatim to window 0, pane 0 of a tmux session.

    No implicit Enter is appended.

    Args:
        session_name: tmux session name (as returned by spawn_worker).
        text: Text to type into the pane.

    Returns:
        ``{"ok": True, "operation": "send_input"}`` on success or an
        SR-7.1 operation-failed dict on failure.
    """
    import asyncio

    try:
        return await asyncio.to_thread(spawn.send_input_impl, session_name, text)
    except Exception as exc:
        return _err("send_input", exc)


@mcp.tool()
async def get_output(session_name: str, scrollback: int = 50) -> dict:
    """Capture recent output from window 0, pane 0 of a tmux session.

    Args:
        session_name: tmux session name (as returned by spawn_worker).
        scrollback: Number of lines to capture.  Must be in [1, 1000];
            out-of-range values return operation-failed (not silently clamped).

    Returns:
        ``{"ok": True, "operation": "get_output", "content": str}`` on
        success or an SR-7.1 operation-failed dict on failure.
    """
    import asyncio

    try:
        return await asyncio.to_thread(spawn.get_output_impl, session_name, scrollback)
    except Exception as exc:
        return _err("get_output", exc)


@mcp.tool()
async def terminate_worker(session_name: str) -> dict:
    """Kill a worker's tmux session.

    Claude Status records the worker as ``ended`` via its lifecycle hooks
    independently.

    Args:
        session_name: tmux session name (as returned by spawn_worker).

    Returns:
        ``{"ok": True, "operation": "terminate_worker"}`` on success or an
        SR-7.1 operation-failed dict on failure.
    """
    import asyncio

    try:
        return await asyncio.to_thread(spawn.terminate_worker_impl, session_name)
    except Exception as exc:
        return _err("terminate_worker", exc)


@mcp.tool()
async def answer_question(question_id: int, answer: str) -> dict:
    """Answer a pending AskUserQuestion via validated tmux send-keys.

    Verifies the question text is visible in the worker's pane before sending.

    Args:
        question_id: The Claude Status ``agent_request.request_id`` of the
            pending AskUserQuestion to answer.
        answer: The answer text to send.  Option-pick answers should be
            stringified by the orchestrator (e.g. ``"2"``).

    Returns:
        ``{"ok": True, "operation": "answer_question"}`` on success or an
        SR-7.1 operation-failed dict on failure.
    """
    import asyncio

    try:
        return await asyncio.to_thread(spawn.answer_question_impl, question_id, answer)
    except Exception as exc:
        return _err("answer_question", exc)


@mcp.tool()
async def list_spawned_workers() -> dict:
    """List all Waggle-owned workers from Claude Status.

    Reads from ``claude-status workers --label waggle_owned=1`` on every call;
    no in-memory state.  Survives Waggle process restarts.

    Returns:
        ``{"workers": [{"instance_id": str, "session_name": str}, ...]}``
        on success or an SR-7.1 operation-failed dict on failure.
        Skipped rows from Claude Status are logged to stderr but excluded
        from the returned list.
    """
    import asyncio

    try:
        return await asyncio.to_thread(spawn.list_spawned_workers_impl)
    except Exception as exc:
        return _err("list_spawned_workers", exc)


def run() -> None:
    """Launch the stdio MCP server.  Blocks until stdin closes."""
    mcp.run()
