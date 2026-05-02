"""Waggle v2 Worker MCP server — workers connect here to register themselves."""

import logging
from typing import Any

from fastmcp import FastMCP, Context
from fastmcp.server.dependencies import get_http_request
from fastmcp.server.middleware import Middleware, MiddlewareContext
from mcp.server.session import ServerSession
from starlette.applications import Starlette
from starlette.routing import Mount

from waggle import config, database

logger = logging.getLogger(__name__)


class WorkerRegistry:
    """In-memory registry mapping worker_id to MCP ServerSession.

    Stores the actual ServerSession object so send_input can call
    session.send_notification() to deliver Claude Channels messages.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, ServerSession] = {}

    def register(self, worker_id: str, session: ServerSession) -> None:
        self._sessions[worker_id] = session

    def unregister(self, worker_id: str) -> None:
        self._sessions.pop(worker_id, None)

    def get(self, worker_id: str) -> ServerSession | None:
        return self._sessions.get(worker_id)


registry = WorkerRegistry()


class WorkerRegistrationMiddleware(Middleware):
    """Auto-registers a worker session during tools/list (MCP client init)."""

    async def on_list_tools(self, context: MiddlewareContext, call_next):
        result = await call_next(context)
        worker_id = None
        try:
            request = get_http_request()
            worker_id = request.query_params.get("worker_id")
            if worker_id:
                session = context.fastmcp_context.session
                existing = registry.get(worker_id)
                if existing is not session:
                    if existing is not None:
                        logger.debug(
                            "Replacing stale session for worker_id=%s (old=%s, new=%s)",
                            worker_id, id(existing), id(session),
                        )
                    registry.register(worker_id, session)
                    db_path = _db_path()
                    mcp_session_id = context.fastmcp_context.session_id
                    with database.connection(db_path) as conn:
                        conn.execute(
                            "UPDATE workers SET mcp_session_id = ? WHERE worker_id = ?",
                            (str(mcp_session_id) if mcp_session_id else None, worker_id),
                        )
        except Exception as e:
            logger.warning("Auto-registration failed for worker_id=%s: %s", worker_id, e)
        return result


worker_mcp = FastMCP("waggle-worker")

_orig_create = worker_mcp._mcp_server.create_initialization_options


def _patched_create(notification_options=None, experimental_capabilities=None, **kwargs):
    ec = dict(experimental_capabilities or {})
    ec["claude/channel"] = {}
    return _orig_create(
        notification_options=notification_options,
        experimental_capabilities=ec,
        **kwargs,
    )


worker_mcp._mcp_server.create_initialization_options = _patched_create
worker_mcp.add_middleware(WorkerRegistrationMiddleware())


def _db_path() -> str:
    from pathlib import Path

    cfg = config.get_config()
    return str(Path(cfg["database_path"]).expanduser().absolute())


@worker_mcp.tool()
async def register_worker(ctx: Context = None) -> dict:
    """Register this worker with waggle.

    Extracts worker_id from the HTTP request query params, validates it
    against the workers table, and stores the MCP session for notification
    delivery.

    Args:
        ctx: MCP context (auto-injected).
    """
    if ctx is None:
        return {"error": "no_context"}

    # Extract worker_id from HTTP request query params
    worker_id = None
    try:
        request = get_http_request()
        worker_id = request.query_params.get("worker_id")
    except (RuntimeError, Exception):
        pass

    if not worker_id:
        return {"error": "worker_id_required"}

    db_path = _db_path()

    # Validate worker exists in DB
    with database.connection(db_path) as conn:
        row = conn.execute(
            "SELECT worker_id FROM workers WHERE worker_id = ?",
            (worker_id,),
        ).fetchone()

    if row is None:
        return {"error": "worker_not_found"}

    # Get MCP session ID and session object
    mcp_session_id = None
    session = None
    try:
        mcp_session_id = ctx.session_id
        session = ctx.session
    except (AttributeError, RuntimeError):
        pass

    # Persist session ID to DB
    with database.connection(db_path) as conn:
        conn.execute(
            "UPDATE workers SET mcp_session_id = ? WHERE worker_id = ?",
            (str(mcp_session_id) if mcp_session_id else None, worker_id),
        )

    # Store ServerSession in registry for notification delivery
    if session is not None:
        registry.register(worker_id, session)

    return {"worker_id": worker_id, "registered": True}


def create_worker_app() -> Starlette:
    """Build the Starlette application with worker FastMCP mounted at /mcp."""
    worker_mcp_http_app = worker_mcp.http_app(path="/")
    return Starlette(
        routes=[
            Mount("/mcp", app=worker_mcp_http_app),
        ],
        lifespan=worker_mcp_http_app.lifespan,
    )


worker_app = create_worker_app()
