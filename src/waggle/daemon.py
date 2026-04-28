"""Waggle v2 HTTP daemon — Uvicorn startup and signal handling."""

import asyncio
from pathlib import Path

import uvicorn

from waggle import rest
from waggle.config import get_config, get_db_path, get_http_port, get_mcp_worker_port
from waggle.database import init_schema
from waggle.inbound_processor import process_inbound
from waggle.outbound_processor import process_outbound
from waggle.queue import get_inbound_queue, get_outbound_queue


async def _run() -> None:
    """Start waggle orchestrator and worker MCP servers concurrently."""
    init_schema(get_db_path())

    cfg = get_config()
    queue_path = str(Path(cfg["queue_path"]).expanduser().absolute())

    inbound_q = get_inbound_queue(queue_path)
    outbound_q = get_outbound_queue(queue_path)
    rest.set_inbound_queue(inbound_q)

    # TLS config
    ssl_kwargs = {}
    tls_cert = cfg.get("tls_cert_path", "")
    tls_key = cfg.get("tls_key_path", "")
    if tls_cert and tls_key:
        ssl_kwargs = {
            "ssl_certfile": str(Path(tls_cert).expanduser()),
            "ssl_keyfile": str(Path(tls_key).expanduser()),
        }

    config1 = uvicorn.Config(
        "waggle.server:app",
        host="127.0.0.1",
        port=get_http_port(),
        log_level="info",
        **ssl_kwargs,
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
    await asyncio.gather(
        server1.serve(),
        server2.serve(),
        process_inbound(inbound_q),
        process_outbound(outbound_q),
    )


def run() -> None:
    """Start the waggle daemon."""
    asyncio.run(_run())
