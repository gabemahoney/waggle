"""Waggle v2 MCP server — thin tool adapters over the core engine."""

from fastmcp import FastMCP, Context
from starlette.applications import Starlette
from starlette.routing import Mount

from waggle import engine
from waggle.middleware import SSHAuthMiddleware
from waggle.rest import rest_router

mcp = FastMCP("waggle")


def _get_caller_id(ctx: Context | None) -> str:
    """Derive caller_id from MCP context.

    Uses the MCP session ID if available, falls back to "local".
    """
    if ctx is None:
        return "local"
    try:
        session_id = ctx.session_id
        if session_id:
            return str(session_id)
    except (AttributeError, Exception):
        pass
    return "local"


@mcp.tool()
async def register_caller(caller_type: str = "local", ctx: Context = None) -> dict:
    """Register this caller with waggle.

    Args:
        caller_type: "local" or "cma". Default "local".
        ctx: MCP context (auto-injected).
    """
    caller_id = _get_caller_id(ctx)
    return await engine.register_caller(caller_id, caller_type)


@mcp.tool()
async def spawn_worker(model: str, repo: str, session_name: str | None = None, ctx: Context = None) -> dict:
    """Spawn a new worker.

    Args:
        model: Claude model name (e.g. "sonnet", "haiku", "opus").
        repo: Local path or GitHub HTTPS URL.
        session_name: Optional tmux session name.
        ctx: MCP context (auto-injected).
    """
    caller_id = _get_caller_id(ctx)
    return await engine.spawn_worker(caller_id, model, repo, session_name)


@mcp.tool()
async def list_workers(ctx: Context = None) -> dict:
    """List all workers for this caller.

    Args:
        ctx: MCP context (auto-injected).
    """
    caller_id = _get_caller_id(ctx)
    workers = await engine.list_workers(caller_id)
    return {"workers": workers}


@mcp.tool()
async def check_status(worker_id: str, ctx: Context = None) -> dict:
    """Check status of a specific worker.

    Args:
        worker_id: Worker UUID to check.
        ctx: MCP context (auto-injected).
    """
    caller_id = _get_caller_id(ctx)
    return await engine.check_status(caller_id, worker_id)


@mcp.tool()
async def get_output(worker_id: str, scrollback: int = 200, ctx: Context = None) -> dict:
    """Get recent output from a worker's pane.

    Args:
        worker_id: Worker UUID.
        scrollback: Lines of scrollback to capture (default 200).
        ctx: MCP context (auto-injected).
    """
    caller_id = _get_caller_id(ctx)
    return await engine.get_output(caller_id, worker_id, scrollback)


@mcp.tool()
async def send_input(worker_id: str, text: str, ctx: Context = None) -> dict:
    """Send text input to a worker via Claude Channels.

    Args:
        worker_id: Worker UUID to send input to.
        text: Text content to deliver.
        ctx: MCP context (auto-injected).
    """
    caller_id = _get_caller_id(ctx)
    return await engine.send_input(caller_id, worker_id, text)


@mcp.tool()
async def approve_permission(worker_id: str, decision: str, ctx: Context = None) -> dict:
    """Approve or deny a worker's pending permission request.

    Args:
        worker_id: Worker UUID with the pending permission request.
        decision: "allow" or "deny".
        ctx: MCP context (auto-injected).
    """
    caller_id = _get_caller_id(ctx)
    return await engine.approve_permission(caller_id, worker_id, decision)


@mcp.tool()
async def answer_question(worker_id: str, answer: str, ctx: Context = None) -> dict:
    """Answer a worker's pending question.

    Args:
        worker_id: Worker UUID with the pending question.
        answer: The answer text.
        ctx: MCP context (auto-injected).
    """
    caller_id = _get_caller_id(ctx)
    return await engine.answer_question(caller_id, worker_id, answer)


@mcp.tool()
async def terminate_worker(worker_id: str, force: bool = False, ctx: Context = None) -> dict:
    """Terminate a worker and clean up its resources.

    Args:
        worker_id: Worker UUID to terminate.
        force: Reserved for future use.
        ctx: MCP context (auto-injected).
    """
    caller_id = _get_caller_id(ctx)
    return await engine.terminate_worker(caller_id, worker_id, force)


def create_app() -> Starlette:
    """Build the Starlette application with FastMCP mounted at /mcp and REST at /api/v1."""
    starlette_app = Starlette(
        routes=[
            Mount("/mcp", app=mcp.http_app()),
            Mount("/api/v1", app=rest_router),
        ],
    )
    starlette_app.add_middleware(SSHAuthMiddleware)
    return starlette_app


app = create_app()
