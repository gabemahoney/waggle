"""Waggle v2 HTTP daemon — Uvicorn startup and signal handling."""

import asyncio

import uvicorn

from waggle.config import get_db_path, get_http_port, get_mcp_worker_port
from waggle.database import init_schema


async def _run() -> None:
    """Start waggle orchestrator and worker MCP servers concurrently."""
    init_schema(get_db_path())

    config1 = uvicorn.Config(
        "waggle.server:app",
        host="127.0.0.1",
        port=get_http_port(),
        log_level="info",
    )
    config2 = uvicorn.Config(
        "waggle.worker_mcp:worker_app",
        host="127.0.0.1",
        port=get_mcp_worker_port(),
        log_level="info",
    )

    server1 = uvicorn.Server(config1)
    server2 = uvicorn.Server(config2)

    # Uvicorn handles SIGTERM/SIGINT gracefully by default
    await asyncio.gather(server1.serve(), server2.serve())


def run() -> None:
    """Start the waggle daemon."""
    asyncio.run(_run())
