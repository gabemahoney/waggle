"""Async-safe libtmux wrappers for tmux interaction.

Provides session enumeration, LLM detection, and error handling.
All libtmux calls are synchronous — async wrappers offload to threads.
Server() is instantiated per-call (no module-level side effects).
"""

import asyncio
import re
import subprocess
from pathlib import Path
from urllib.parse import urlparse

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
    except Exception:
        return []


def is_llm_running(pane: libtmux.Pane) -> bool:
    """Check if a pane is running an LLM agent.

    Checks pane_current_command for 'claude' (case-insensitive).
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
        return cmd.lower() == "claude"
    except Exception:
        return False


async def get_sessions_async() -> list[dict]:
    """Async wrapper for get_sessions()."""
    return await asyncio.to_thread(get_sessions)


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


def _check_llm_running_sync(session_id: str) -> bool:
    try:
        server = libtmux.Server()
        session = server.sessions.get(session_id=session_id)
        pane = session.active_window.active_pane
        return is_llm_running(pane)
    except Exception:
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



def _create_session_sync(session_name: str, repo_path: str, worker_id: str) -> dict:
    try:
        server = libtmux.Server()
        session = server.new_session(
            session_name=session_name,
            start_directory=repo_path,
            attach=False,
            environment={"VIRTUAL_ENV": "", "VIRTUAL_ENV_PROMPT": ""},
        )
        session.set_environment("WAGGLE_WORKER_ID", worker_id)
        return {
            "status": "success",
            "session_id": session.session_id,
            "session_name": session.session_name,
            "session_created": session.session_created,
            "worker_id": worker_id,
        }
    except LibTmuxException as e:
        return {"status": "error", "message": str(e)}
    except Exception as e:
        return {"status": "error", "message": str(e)}


async def create_session(session_name: str, repo_path: str, worker_id: str) -> dict:
    """Create a new tmux session at the given directory.

    Sets the WAGGLE_WORKER_ID environment variable in the session.

    Args:
        session_name: Name for the new tmux session.
        repo_path: Absolute path to use as the session's start directory.
        worker_id: Worker UUID to set as WAGGLE_WORKER_ID in the session env.

    Returns:
        {"status": "success", "session_id": str, "session_name": str,
         "session_created": str, "worker_id": str}
        or {"status": "error", "message": str}
    """
    return await asyncio.to_thread(_create_session_sync, session_name, repo_path, worker_id)


def _launch_agent_in_pane_sync(
    session_id: str,
    model: str,
    settings: str | None,
) -> dict:
    try:
        server = libtmux.Server()
        session = server.sessions.get(session_id=session_id)
        pane = session.active_window.active_pane
        cmd = f"claude --model {model.lower()}"
        if settings:
            # Only allow characters valid in CLI flags to prevent shell injection
            if re.search(r'[;&|`$(){}\\<>]', settings):
                return {"status": "error", "message": "invalid characters in settings parameter"}
            cmd += f" {settings}"
        pane.send_keys(cmd, enter=True)
        return {"status": "success"}
    except LibTmuxException as e:
        return {"status": "error", "message": str(e)}
    except Exception as e:
        return {"status": "error", "message": str(e)}


async def launch_agent_in_pane(
    session_id: str,
    model: str,
    settings: str | None = None,
) -> dict:
    """Send a claude launch command to the active pane of a session.

    Args:
        session_id: The tmux session ID (e.g. "$1").
        model: Model name (e.g. "sonnet", "haiku", "opus").
        settings: Optional extra CLI flags (e.g. "--dangerously-skip-permissions").

    Returns:
        {"status": "success"} or {"status": "error", "message": str}
    """
    return await asyncio.to_thread(_launch_agent_in_pane_sync, session_id, model, settings)


def clone_or_update_repo(repo: str, repos_path: str) -> str:
    """Clone or update a git repository.

    If repo is a local path (not starting with https://), returns it unchanged.
    If repo is a GitHub HTTPS URL, clones to {repos_path}/{owner}/{repo_name}.
    If the clone already exists, runs git fetch origin && git reset --hard origin/HEAD.

    Args:
        repo: Local path or GitHub HTTPS URL.
        repos_path: Base directory for cloned repositories.

    Returns:
        Absolute local path to the repository.

    Raises:
        ValueError: If the URL cannot be parsed.
        subprocess.CalledProcessError: If git commands fail.
    """
    if not repo.startswith("https://"):
        return repo

    parsed = urlparse(repo)
    # Strip leading slash and .git suffix for path parsing
    path_parts = parsed.path.strip("/").removesuffix(".git").split("/")
    if len(path_parts) < 2:
        raise ValueError(f"Cannot parse owner/repo from URL: {repo}")
    owner, repo_name = path_parts[0], path_parts[1]

    local_path = Path(repos_path) / owner / repo_name

    if local_path.exists():
        subprocess.run(
            ["git", "fetch", "origin"],
            cwd=str(local_path),
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "reset", "--hard", "origin/HEAD"],
            cwd=str(local_path),
            check=True,
            capture_output=True,
        )
    else:
        local_path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "clone", repo, str(local_path)],
            check=True,
            capture_output=True,
        )

    return str(local_path)


async def clone_or_update_repo_async(repo: str, repos_path: str) -> str:
    """Async wrapper for clone_or_update_repo()."""
    return await asyncio.to_thread(clone_or_update_repo, repo, repos_path)
