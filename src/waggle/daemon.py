"""Waggle v2 HTTP daemon — Uvicorn startup and signal handling."""

import uvicorn

from waggle.config import get_http_port, get_db_path
from waggle.database import init_schema


def run():
    """Start the waggle HTTP daemon."""
    # Init schema on startup
    init_schema(get_db_path())

    port = get_http_port()

    config = uvicorn.Config(
        "waggle.server:app",
        host="127.0.0.1",
        port=port,
        log_level="info",
    )
    server = uvicorn.Server(config)

    # Uvicorn handles SIGTERM/SIGINT gracefully by default
    server.run()
