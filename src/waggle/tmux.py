"""Async-safe libtmux wrappers for tmux interaction.

Provides session enumeration, LLM detection, and error handling.
All libtmux calls are synchronous — async wrappers offload to threads.
Server() is instantiated per-call (no module-level side effects).
"""

import asyncio

import libtmux
from libtmux.exc import LibTmuxException


def get_sessions() -> list[dict]:
    """Enumerate tmux sessions with path info.

    Returns list of dicts with keys: session_name, session_id,
    session_created, session_path. Replaces the TMUX_FMT_WITH_PATH
    subprocess pattern.

    Returns empty list if tmux is unavailable or any error occurs.
    """
    try:
        server = libtmux.Server()
        sessions = server.sessions
        result = []
        for s in sessions:
            result.append({
                "session_name": s.session_name,
                "session_id": s.session_id,
                "session_created": s.session_created,
                "session_path": s.session_path,
            })
        return result
    except (LibTmuxException, Exception):
        return []


def get_active_session_keys() -> set[str]:
    """Get composite keys for all active tmux sessions.

    Returns set of strings in format "{name}+{session_id}+{created}".
    Replaces the TMUX_FMT_KEYS_ONLY subprocess pattern used by
    cleanup_dead_sessions for orphan detection.

    Returns empty set if tmux is unavailable or any error occurs.
    """
    try:
        sessions = get_sessions()
        return {
            f"{s['session_name']}+{s['session_id']}+{s['session_created']}"
            for s in sessions
        }
    except (LibTmuxException, Exception):
        return set()


def is_llm_running(pane: libtmux.Pane) -> bool:
    """Check if a pane is running an LLM agent.

    Checks pane_current_command for 'claude' or 'opencode' (case-insensitive).
    Single tmux query only — no process tree walking, no pgrep/psutil (SR-8.1).

    Args:
        pane: libtmux Pane object to inspect.

    Returns:
        True if pane is running an LLM, False otherwise or on error.
    """
    try:
        cmd = pane.pane_current_command
        if cmd is None:
            return False
        return cmd.lower() in ("claude", "opencode")
    except (LibTmuxException, Exception):
        return False


async def get_sessions_async() -> list[dict]:
    """Async wrapper for get_sessions()."""
    return await asyncio.to_thread(get_sessions)


async def get_active_session_keys_async() -> set[str]:
    """Async wrapper for get_active_session_keys()."""
    return await asyncio.to_thread(get_active_session_keys)
