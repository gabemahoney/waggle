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


def _kill_session_sync(session_id: str) -> dict:
    try:
        server = libtmux.Server()
        session = server.sessions.get(session_id=session_id)
        session.kill()
        return {"status": "success"}
    except LibTmuxException as e:
        return {"status": "error", "message": str(e)}
    except Exception as e:
        return {"status": "error", "message": str(e)}


async def kill_session(session_id: str) -> dict:
    """Kill a tmux session by session ID.

    Args:
        session_id: The tmux session ID (e.g. "$1").

    Returns:
        {"status": "success"} or {"status": "error", "message": ...}
    """
    return await asyncio.to_thread(_kill_session_sync, session_id)


def _validate_session_name_id_sync(session_id: str, session_name: str) -> dict:
    try:
        server = libtmux.Server()
        session = server.sessions.get(session_id=session_id)
        if session.session_name == session_name:
            return {"status": "success"}
        return {
            "status": "error",
            "message": (
                f"Session name mismatch: expected '{session_name}', "
                f"found '{session.session_name}'"
            ),
        }
    except LibTmuxException as e:
        return {"status": "error", "message": str(e)}
    except Exception as e:
        return {"status": "error", "message": str(e)}


async def validate_session_name_id(session_id: str, session_name: str) -> dict:
    """Validate that a tmux session ID maps to the expected session name.

    Args:
        session_id: The tmux session ID (e.g. "$1").
        session_name: The expected session name.

    Returns:
        {"status": "success"} or {"status": "error", "message": ...}
    """
    return await asyncio.to_thread(_validate_session_name_id_sync, session_id, session_name)


def _check_llm_running_sync(session_id: str) -> bool:
    try:
        server = libtmux.Server()
        session = server.sessions.get(session_id=session_id)
        pane = session.active_window.active_pane
        return is_llm_running(pane)
    except (LibTmuxException, Exception):
        return False


async def check_llm_running(session_id: str) -> bool:
    """Check if the active pane of a tmux session is running an LLM.

    Args:
        session_id: The tmux session ID (e.g. "$1").

    Returns:
        True if an LLM agent is running, False otherwise or on error.
    """
    return await asyncio.to_thread(_check_llm_running_sync, session_id)


def _capture_pane_sync(session_id: str, pane_id: str | None, scrollback: int) -> dict:
    try:
        server = libtmux.Server()
        session = server.sessions.get(session_id=session_id)
        if pane_id is None:
            pane = session.active_window.active_pane
        else:
            pane = server.panes.get(pane_id=pane_id)
            if pane.session_id != session_id:
                return {
                    "status": "error",
                    "message": f"Pane '{pane_id}' does not belong to session '{session_id}'",
                }
        lines = pane.capture_pane(start=-scrollback)
        return {"status": "success", "content": "\n".join(lines)}
    except LibTmuxException as e:
        return {"status": "error", "message": str(e)}
    except Exception as e:
        return {"status": "error", "message": str(e)}


async def capture_pane(session_id: str, pane_id: str | None = None, scrollback: int = 50) -> dict:
    """Capture content from a tmux pane.

    Args:
        session_id: The tmux session ID (e.g. "$1").
        pane_id: Optional pane ID. If None, uses the active pane.
        scrollback: Number of lines of scrollback to capture.

    Returns:
        {"status": "success", "content": str} or {"status": "error", "message": str}
    """
    return await asyncio.to_thread(_capture_pane_sync, session_id, pane_id, scrollback)


def _validate_pane_id_sync(session_id: str, pane_id: str) -> dict:
    try:
        server = libtmux.Server()
        session = server.sessions.get(session_id=session_id)
        pane = server.panes.get(pane_id=pane_id)
        if pane.session_id != session_id:
            return {
                "status": "error",
                "message": f"Pane '{pane_id}' does not belong to session '{session_id}'",
            }
        return {"status": "success"}
    except LibTmuxException as e:
        return {"status": "error", "message": str(e)}
    except Exception as e:
        return {"status": "error", "message": str(e)}


async def validate_pane_id(session_id: str, pane_id: str) -> dict:
    """Validate that a pane ID belongs to the given session.

    Args:
        session_id: The tmux session ID (e.g. "$1").
        pane_id: The pane ID to validate.

    Returns:
        {"status": "success"} or {"status": "error", "message": str}
    """
    return await asyncio.to_thread(_validate_pane_id_sync, session_id, pane_id)


def _resolve_pane(server: libtmux.Server, session_id: str, pane_id: str | None):
    """Resolve a pane object from session_id and optional pane_id.

    Raises LibTmuxException or ValueError on failure.
    Returns (pane, error_dict) where error_dict is None on success.
    """
    session = server.sessions.get(session_id=session_id)
    if pane_id is None:
        return session.active_window.active_pane, None
    pane = server.panes.get(pane_id=pane_id)
    if pane.session_id != session_id:
        return None, {
            "status": "error",
            "message": f"Pane '{pane_id}' does not belong to session '{session_id}'",
        }
    return pane, None


def _send_keys_to_pane_sync(session_id: str, text: str, pane_id: str | None, enter: bool) -> dict:
    try:
        server = libtmux.Server()
        pane, err = _resolve_pane(server, session_id, pane_id)
        if err:
            return err
        pane.send_keys(text, enter=enter)
        return {"status": "success"}
    except LibTmuxException as e:
        return {"status": "error", "message": str(e)}
    except Exception as e:
        return {"status": "error", "message": str(e)}


async def send_keys_to_pane(
    session_id: str,
    text: str,
    pane_id: str | None = None,
    enter: bool = True,
) -> dict:
    """Send keys to a tmux pane.

    Args:
        session_id: The tmux session ID (e.g. "$1").
        text: The text/keys to send.
        pane_id: Optional pane ID. If None, uses the active pane.
        enter: If True, sends Enter after the text.

    Returns:
        {"status": "success"} or {"status": "error", "message": str}
    """
    return await asyncio.to_thread(_send_keys_to_pane_sync, session_id, text, pane_id, enter)


def _clear_pane_input_sync(session_id: str, pane_id: str | None) -> dict:
    try:
        server = libtmux.Server()
        pane, err = _resolve_pane(server, session_id, pane_id)
        if err:
            return err
        pane.send_keys("C-c", enter=False)
        return {"status": "success"}
    except LibTmuxException as e:
        return {"status": "error", "message": str(e)}
    except Exception as e:
        return {"status": "error", "message": str(e)}


async def clear_pane_input(session_id: str, pane_id: str | None = None) -> dict:
    """Send Ctrl+C to clear partial input in a tmux pane.

    Args:
        session_id: The tmux session ID (e.g. "$1").
        pane_id: Optional pane ID. If None, uses the active pane.

    Returns:
        {"status": "success"} or {"status": "error", "message": str}
    """
    return await asyncio.to_thread(_clear_pane_input_sync, session_id, pane_id)
