"""Configuration management for Waggle.

Reads configuration from ~/.waggle/config.json with intelligent defaults.
Handles missing files, malformed JSON, and provides fallback values.
"""

import json
from pathlib import Path
from typing import Any, Dict


_DEFAULTS: Dict[str, Any] = {
    "database_path": "~/.waggle/state.db",
    "queue_path": "~/.waggle/queue.db",
    "max_workers": 8,
    "state_poll_interval_seconds": 2,
    "output_capture_lines": 50,
    "http_port": 8422,
    "mcp_worker_port": 8423,
    "relay_timeout_seconds": 3600,
    "authorized_keys_path": "~/.waggle/authorized_keys.json",
    "repos_path": "~/.waggle/repos",
    "admin_email": "",
    "admin_notify_after_retries": 5,
    "max_retry_hours": 72,
    "tls_cert_path": "",
    "tls_key_path": "",
}


def get_config() -> Dict[str, Any]:
    """Read ~/.waggle/config.json merged over defaults.

    File values override defaults; unknown keys in the file are ignored.
    Returns all v2 keys with correct defaults when config file is missing or
    malformed.

    Returns:
        Dict containing all v2 configuration keys with resolved values
    """
    config_file = Path.home() / ".waggle" / "config.json"

    file_config: Dict[str, Any] = {}
    if config_file.exists():
        try:
            with open(config_file, "r") as f:
                parsed = json.load(f)
            if isinstance(parsed, dict):
                file_config = parsed
        except (json.JSONDecodeError, OSError):
            pass

    # Merge: only known keys, file wins
    return {k: file_config[k] if k in file_config else v for k, v in _DEFAULTS.items()}


def get_db_path() -> str:
    """Return tilde-expanded absolute path to the state database."""
    return str(Path(get_config()["database_path"]).expanduser().absolute())


def get_queue_path() -> str:
    """Return tilde-expanded absolute path to the queue database."""
    return str(Path(get_config()["queue_path"]).expanduser().absolute())


def get_http_port() -> int:
    """Return the HTTP server port."""
    return int(get_config()["http_port"])


def get_mcp_worker_port() -> int:
    """Return the MCP worker port."""
    return int(get_config()["mcp_worker_port"])


def get_max_workers() -> int:
    """Return the maximum number of concurrent workers."""
    return int(get_config()["max_workers"])


def get_repos_path() -> str:
    """Return tilde-expanded absolute path to the repos directory."""
    return str(Path(get_config()["repos_path"]).expanduser().absolute())
