"""MCP Server for Waggle Agent State Management.

Provides FastMCP server initialization with database integration.
"""

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse, unquote
from fastmcp import FastMCP, Context
from fastmcp.exceptions import NotFoundError
from mcp.shared.exceptions import McpError

from waggle.config import get_db_path
from waggle.database import init_schema, connection
from waggle import state_parser
from waggle.tmux import (
    get_sessions,
    get_active_session_keys,
    kill_session,
    validate_session_name_id,
    check_llm_running,
    capture_pane,
    send_keys_to_pane,
    clear_pane_input,
    create_session,
    launch_agent_in_pane,
    resolve_session,
)

# Initialize FastMCP instance
mcp = FastMCP("waggle-async-agents")


async def get_client_repo_root(ctx: Context) -> Path | None:
    """Extract repository root from MCP client context if client supports roots protocol.
    
    Args:
        ctx: FastMCP Context object provided by MCP client
        
    Returns:
        Path if client supports roots and provides them, None otherwise
    """
    try:
        roots = await ctx.list_roots()
        
        if not roots:
            return None
        
        # Take first root and convert to Path
        first_root = roots[0]
        root_uri_str = str(first_root.uri)
        
        # Parse file:// URI properly
        if root_uri_str.startswith("file://"):
            parsed = urlparse(root_uri_str)
            # Handle both file:///path and file://localhost/path
            # For file:///path, netloc is empty and path contains the path
            # For file://localhost/path, netloc is 'localhost' and path contains the path
            root_path = unquote(parsed.path)
        else:
            root_path = root_uri_str
        
        return Path(root_path)
    
    except (NotFoundError, McpError):
        # Method not found means client doesn't support roots
        return None


def normalize_path(path_str: str) -> str:
    """Normalize a path to match the format used by pwd in hooks.

    Converts to absolute path and removes trailing slashes, but does NOT
    resolve symlinks (to match pwd behavior).

    Args:
        path_str: Path string to normalize

    Returns:
        Normalized absolute path without trailing slash
    """
    # Convert to Path object and make absolute
    p = Path(path_str).expanduser().absolute()

    # Convert back to string, this normalizes . and .. but keeps symlinks
    normalized = str(p)

    # Remove trailing slash if present (unless it's just "/")
    if len(normalized) > 1 and normalized.endswith('/'):
        normalized = normalized.rstrip('/')

    return normalized


async def resolve_repo_root(ctx: Optional[Context], explicit_root: str | None) -> str:
    """Resolve repository root from MCP client context or explicit parameter.

    Tries MCP client's roots protocol first, falls back to explicit parameter.
    Normalizes the path to match pwd format used by hooks.

    Args:
        ctx: FastMCP Context object provided by MCP client (or None)
        explicit_root: Optional explicit repo_root path string (fallback)

    Returns:
        Normalized repository root path as string

    Raises:
        ValueError: If neither roots protocol nor explicit_root are available
    """
    raw_root = None

    # Try Roots protocol first if ctx is provided
    if ctx is not None:
        client_root = await get_client_repo_root(ctx)
        if client_root:
            raw_root = str(client_root)

    # Fall back to explicit parameter
    if raw_root is None and explicit_root:
        raw_root = explicit_root

    # Neither available - raise error
    if raw_root is None:
        raise ValueError(
            "Your MCP client does not support the roots protocol. "
            "Please provide repo_root parameter when calling this tool."
        )

    # Normalize the path to match pwd format
    normalized = normalize_path(raw_root)
    return normalized


@mcp.tool()
async def list_agents(
    name: Optional[str] = None,
    repo: Optional[str] = None,
    ctx: Optional[Context] = None
) -> dict:
    """List all active async agents with their status.
    
    Queries tmux sessions to find Claude and OpenCode instances. Reports back their state (waiting, working, etc).
    Returns all agents system-wide with optional filtering by repository path.

    ## Output Formatting

    When responding to user, use this markdown table format (backticks render status in blue):

    | Name | Status | Directory | ID |
    |------|--------|-----------|-----|
    | agent-abc123 | `working` | /path/to/project1 | $1 |
    | agent-def456 | `waiting` | /path/to/project2 | $2 |

    Notes:
    - Use backticks around status values to render them as inline code (blue)
    - If directory is too long (~30 chars), truncate from front: .../projects/project1 not /Users/user/projects/...

    Args:
        name: Optional filter to return only sessions matching this name
        repo: Optional filter to return only agents whose namespace contains this substring (case-insensitive)
        ctx: FastMCP Context (auto-injected)
        
    Returns:
        dict: Success dict with agents list OR error dict
            Success: {"status": "success", "agents": [{"name": str, "session_id": str, 
                      "directory": str, "status": str, "namespace": str | None}, ...]}
            Error: {"status": "error", "error": str}
    """
    # Clean up dead sessions before querying
    cleanup_dead_sessions()

    # Query database for registered agents (DB as source of truth)
    db_path = get_db_path()
    try:
        with connection(db_path) as conn:
            cursor = conn.cursor()
            # Query all state entries
            cursor.execute("SELECT key, repo, status FROM state")
            state_entries = cursor.fetchall()
            
            # Build agents list from DB entries
            agents = []
            for key, repo_path, status in state_entries:
                # Key format: name+session_id+session_created
                parts = key.split('+', 2)
                if len(parts) != 3:
                    continue  # Skip malformed keys
                
                session_name, session_id, session_created = parts[0], parts[1], parts[2]
                
                # Apply name filter if provided
                if name is not None and session_name != name:
                    continue
                
                # Apply repo filter if provided
                if repo is not None:
                    repo_lower = repo.lower()
                    if repo_path is None or repo_lower not in repo_path.lower():
                        continue
                
                agents.append({
                    "name": session_name,
                    "session_id": session_id,
                    "session_created": session_created,
                    "status": status,
                    "repo": repo_path,
                    "directory": None  # Will enrich with tmux data
                })
    except Exception as e:
        return {
            "status": "error",
            "error": f"Failed to query database: {str(e)}"
        }
    
    # Enrich with tmux session paths (non-fatal — get_sessions returns [] on error)
    tmux_session_list = get_sessions()
    tmux_sessions = {}
    for s in tmux_session_list:
        composite_key = f"{s['session_name']}+{s['session_id']}+{s['session_created']}"
        tmux_sessions[composite_key] = s["session_path"]

    for agent in agents:
        composite_key = f"{agent['name']}+{agent['session_id']}+{agent['session_created']}"
        if composite_key in tmux_sessions:
            agent["directory"] = tmux_sessions[composite_key]
    
    return {
        "status": "success",
        "agents": agents
    }


@mcp.tool()
async def delete_repo_agents(
    repo_root: Optional[str] = None,
    ctx: Optional[Context] = None
) -> dict:
    """Delete all agent state for a specific repository.
    
    Nuclear option for cleaning up stale or corrupted state. Deletes all database
    entries for the specified repository but does NOT terminate tmux sessions.
    
    Args:
        repo_root: Repository root path (fallback if roots protocol unavailable)
        ctx: FastMCP Context (auto-injected)
        
    Returns:
        dict: Success dict with deletion count OR error dict
            Success: {"status": "success", "deleted_count": int}
            Error: {"status": "error", "error": str}
    """
    try:
        # Get namespace for state filtering
        namespace = await resolve_repo_root(ctx, repo_root)
    except ValueError as e:
        return {
            "status": "error",
            "error": str(e)
        }
    
    # Delete all entries for this namespace
    db_path = get_db_path()
    try:
        with connection(db_path) as conn:
            cursor = conn.cursor()
            
            # Delete all entries for this namespace and subdirectories
            cursor.execute(
                "DELETE FROM state WHERE repo = ? OR repo LIKE ?",
                (namespace, f"{namespace}/%")
            )
            deleted_count = cursor.rowcount
            
            return {
                "status": "success",
                "deleted_count": deleted_count
            }
            
    except Exception as e:
        return {
            "status": "error",
            "error": f"Failed to clean up database: {str(e)}"
        }


def _lookup_session_key(db_path: str, session_id: str) -> tuple[str | None, dict | None]:
    """Look up the DB key for a session_id.

    Returns:
        (matching_key, None) on success
        (None, error_dict) on DB error or not found
    """
    try:
        with connection(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT key FROM state WHERE key LIKE ?",
                (f"%+{session_id}+%",),
            )
            rows = cursor.fetchall()
            matching_key = rows[0][0] if rows else None
    except Exception as e:
        return None, {"status": "error", "message": f"Failed to query database: {str(e)}"}

    if matching_key is None:
        return None, {"status": "error", "message": f"Session '{session_id}' not found in database"}

    return matching_key, None


@mcp.tool()
async def close_session(
    session_id: str,
    session_name: str | None = None,
    force: bool = False,
) -> dict:
    """Close an agent tmux session and remove its database entry.

    Terminates a tmux session managed by waggle. DB entry is removed first;
    if the tmux kill subsequently fails, the error is reported but the DB
    entry is already gone.

    Args:
        session_id: The tmux session ID (e.g. "$1"). Required.
        session_name: Optional name to validate against — prevents closing the
            wrong session if IDs have been recycled.
        force: If True, close even if an LLM agent is actively running.

    Returns:
        {"status": "success", "message": "Session closed"} or
        {"status": "error", "message": ...}
    """
    db_path = get_db_path()

    # Step 1: Validate session_id exists in DB
    matching_key, err = _lookup_session_key(db_path, session_id)
    if err:
        return err

    # Step 2: Validate session_name if provided
    if session_name is not None:
        result = await validate_session_name_id(session_id, session_name)
        if result["status"] != "success":
            return result

    # Step 3: Check if LLM is running
    llm_running = await check_llm_running(session_id)

    # Steps 4–5: Enforce force flag
    if llm_running and not force:
        return {
            "status": "error",
            "message": "Active LLM agent, call again with force=true to confirm",
        }

    # Step 6: DB-first delete
    try:
        with connection(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM state WHERE key = ?", (matching_key,))
    except Exception as e:
        return {"status": "error", "message": f"Failed to delete database entry: {str(e)}"}

    # Step 7: Kill the tmux session
    kill_result = await kill_session(session_id)

    # Step 8: Report partial failure if kill failed
    if kill_result["status"] != "success":
        return {
            "status": "error",
            "message": (
                f"DB entry removed but tmux session kill failed: "
                f"{kill_result.get('message', 'unknown error')}"
            ),
        }

    # Step 9: Success
    return {"status": "success", "message": "Session closed"}


@mcp.tool()
async def read_pane(
    session_id: str,
    pane_id: str | None = None,
    scrollback: int = 50,
) -> dict:
    """Read content from an agent's tmux pane and detect its current state.

    Captures the visible pane output and classifies the agent state
    (working, done, ask_user, check_permission, or unknown).

    Args:
        session_id: The tmux session ID (e.g. "$1"). Required.
        pane_id: Optional pane ID. If None, uses the session's active pane.
        scrollback: Number of lines of scrollback to capture. Default 50.

    Returns:
        On success:
            {
                "status": "success",
                "agent_state": "ask_user" | "check_permission" | "working" | "done" | "unknown",
                "content": str,       # Raw pane text
                "prompt_data": {      # Only populated for ask_user and check_permission
                    # ask_user — agent is asking a question with numbered options:
                    #   "question": str           — the question text
                    #   "options": [              — list of choices
                    #       {
                    #           "number": int,    — pass this to send_command as command
                    #           "label": str,     — human-readable label
                    #           "description": str
                    #       }, ...
                    #   ]
                    #   One option will always be labelled "Type something." — to choose it,
                    #   pass its number as command AND provide custom_text to send_command.
                    #
                    # check_permission — agent wants approval to run a tool:
                    #   "tool_type": str, "command": str, "description": str
                    #   Pass "1" to approve or "2" to deny via send_command.
                } | None
            }
        On error:
            {"status": "error", "message": str}
    """
    db_path = get_db_path()

    # Step 1: Validate session_id exists in DB
    matching_key, err = _lookup_session_key(db_path, session_id)
    if err:
        return err

    # Step 2: Capture pane content
    capture_result = await capture_pane(session_id, pane_id, scrollback)
    if capture_result["status"] != "success":
        return capture_result

    content = capture_result["content"]

    # Step 3: Parse state from content
    agent_state, prompt_data = state_parser.parse(content)

    # Step 4: Return result
    return {
        "status": "success",
        "agent_state": agent_state,
        "content": content,
        "prompt_data": prompt_data,
    }


@mcp.tool()
async def send_command(
    session_id: str,
    command: str,
    pane_id: str | None = None,
    custom_text: str | None = None,
) -> dict:
    """Send a command to an agent's tmux pane.

    Validates the agent is in a receptive state before sending, optionally
    validates option numbers for interactive prompts, then polls for a state
    transition to confirm delivery.

    Args:
        session_id: The tmux session ID (e.g. "$1"). Required.
        command: The command text to send to the pane. For ask_user and
            check_permission states this must be a valid option number
            (e.g. "1", "2"). Use read_pane first to discover available options.
        pane_id: Optional pane ID. If None, uses the session's active pane.
        custom_text: Free-form text response for the "Type something." option
            in ask_user prompts. When provided, command must be the number of
            the "Type something." option. The option is selected without Enter,
            then custom_text is typed and submitted.
            Example: command="3", custom_text="teddybear"

    Returns:
        {"status": "success", "message": "command delivered"} or
        {"status": "error", "message": str}
    """
    db_path = get_db_path()

    # Step 1: Validate session_id in DB
    matching_key, err = _lookup_session_key(db_path, session_id)
    if err:
        return err

    # Step 2: Read current pane state
    capture_result = await capture_pane(session_id, pane_id)
    if capture_result["status"] != "success":
        return capture_result

    agent_state, prompt_data = state_parser.parse(capture_result["content"])

    # Step 3: Reject if working
    if agent_state == "working":
        return {"status": "error", "message": "agent is busy"}

    # Step 4: Reject if unknown
    if agent_state == "unknown":
        return {"status": "error", "message": "agent state unknown, cannot safely send"}

    # Step 5: Validate command for ask_user state
    if agent_state == "ask_user":
        if not prompt_data or not prompt_data.get("options"):
            return {"status": "error", "message": "could not parse options from ask_user prompt"}
        valid_numbers = {str(opt["number"]) for opt in prompt_data["options"]}
        if command not in valid_numbers:
            return {
                "status": "error",
                "message": (
                    f"invalid option '{command}'; "
                    f"valid options are: {', '.join(sorted(valid_numbers))}"
                ),
            }
        if custom_text is not None:
            selected = next(
                (opt for opt in prompt_data["options"] if str(opt["number"]) == command),
                None,
            )
            if selected is None or "Type something" not in selected.get("label", ""):
                return {
                    "status": "error",
                    "message": "custom_text can only be used with the 'Type something.' option",
                }

    # Step 6: Validate command for check_permission state
    if agent_state == "check_permission":
        if command not in ("1", "2"):
            return {
                "status": "error",
                "message": "invalid option; must be '1' (yes) or '2' (no) for permission prompts",
            }

    # Step 7: Clear partial input, then send command
    # Skip Ctrl+C clear for interactive dialog states — it would dismiss the prompt
    if agent_state == "done":
        clear_result = await clear_pane_input(session_id, pane_id)
        if clear_result["status"] != "success":
            return clear_result

    if custom_text is not None:
        # "Type something." option: select without Enter to open the text field,
        # then send the custom text with Enter to submit.
        send_result = await send_keys_to_pane(session_id, command, pane_id, enter=False)
        if send_result["status"] != "success":
            return send_result
        await asyncio.sleep(0.3)
        send_result = await send_keys_to_pane(session_id, custom_text, pane_id, enter=True)
    else:
        send_result = await send_keys_to_pane(session_id, command, pane_id)
    if send_result["status"] != "success":
        return send_result

    # Step 8: Poll every 0.5s for up to 5s for state transition
    for _ in range(10):
        await asyncio.sleep(0.5)
        poll_result = await capture_pane(session_id, pane_id)
        if poll_result["status"] != "success":
            continue
        new_state, _ = state_parser.parse(poll_result["content"])
        if new_state != agent_state:
            return {"status": "success", "message": "command delivered"}

    # Step 9: Timeout
    return {
        "status": "error",
        "message": "command delivery unconfirmed: agent did not transition within 5 seconds",
    }


@mcp.tool()
async def spawn_agent(
    repo: str,
    session_name: str,
    agent: str,
    model: str | None = None,
    command: str | None = None,
    settings: str | None = None,
    ctx: Context | None = None,
) -> dict:
    """Launch a Claude or OpenCode agent in a tmux session.

    Creates a new session or reuses an existing one (see SR-6.2), launches the
    agent, registers it in waggle's DB, and optionally delivers an initial command
    once the agent reaches ready state.

    Args:
        repo: Absolute path to the repository directory for the agent.
        session_name: tmux session name to create or reuse.
        agent: Agent type — "claude" or "opencode".
        model: Optional model name (e.g. "sonnet", "haiku", "opus").
        command: Optional initial command to deliver after agent reaches ready state.
        settings: Optional extra CLI flags (e.g. "--dangerously-skip-permissions").

    Returns:
        {"status": "success"|"error", "session_id": str|None, "session_name": str, "message": str}
    """
    if agent.lower() not in ("claude", "opencode"):
        return {
            "status": "error",
            "session_id": None,
            "session_name": session_name,
            "message": f"invalid agent '{agent}'; must be 'claude' or 'opencode'",
        }

    repo_path = str(Path(repo).resolve())
    db_path = get_db_path()

    # Step 1: Resolve session
    resolution = await resolve_session(session_name, repo_path)
    action = resolution["action"]

    if action == "error":
        return {
            "status": "error",
            "session_id": None,
            "session_name": session_name,
            "message": resolution["message"],
        }

    if action == "create":
        create_result = await create_session(session_name, repo_path)
        if create_result["status"] != "success":
            return {
                "status": "error",
                "session_id": None,
                "session_name": session_name,
                "message": create_result["message"],
            }
        session_id = create_result["session_id"]
        session_created = create_result["session_created"]
    else:  # reuse
        session_id = resolution["session_id"]
        session_created = resolution["session_created"]

    # Step 2: Launch agent
    launch_result = await launch_agent_in_pane(session_id, agent, model, settings)
    if launch_result["status"] != "success":
        return {
            "status": "error",
            "session_id": session_id,
            "session_name": session_name,
            "message": launch_result["message"],
        }

    # Step 3: DB registration (SR-6.5)
    try:
        key = f"{session_name}+{session_id}+{session_created}"
        with connection(db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO state (key, repo, status, updated_at) VALUES (?, ?, ?, ?)",
                (key, repo_path, "working", datetime.now(timezone.utc).isoformat()),
            )
    except Exception as e:
        return {
            "status": "error",
            "session_id": session_id,
            "session_name": session_name,
            "message": f"Failed to register agent in database: {str(e)}",
        }

    # Step 4: Without command — return immediately
    if not command:
        return {
            "status": "success",
            "session_id": session_id,
            "session_name": session_name,
            "message": "agent launched",
        }

    # Step 5: With command — poll until done (60s timeout at 1s intervals)
    last_state = "unknown"
    for _ in range(60):
        await asyncio.sleep(1.0)
        poll_result = await capture_pane(session_id)
        if poll_result["status"] != "success":
            continue
        pane_state, _ = state_parser.parse(poll_result["content"])
        last_state = pane_state
        if pane_state == "done":
            clear_result = await clear_pane_input(session_id)
            if clear_result["status"] != "success":
                return {
                    "status": "error",
                    "session_id": session_id,
                    "session_name": session_name,
                    "message": f"Failed to clear pane input: {clear_result['message']}",
                }
            send_result = await send_keys_to_pane(session_id, command)
            if send_result["status"] != "success":
                return {
                    "status": "error",
                    "session_id": session_id,
                    "session_name": session_name,
                    "message": f"Failed to send command: {send_result['message']}",
                }
            return {
                "status": "success",
                "session_id": session_id,
                "session_name": session_name,
                "message": "agent launched and command delivered",
            }

    return {
        "status": "error",
        "session_id": session_id,
        "session_name": session_name,
        "message": f"Agent readiness timeout after 60s. Last state: {last_state}",
    }


def cleanup_dead_sessions():
    """Remove database entries for dead tmux sessions.

    Queries tmux via libtmux for active sessions and removes database entries
    for sessions that no longer exist. Silently handles all errors.
    """
    try:
        active_sessions = get_active_session_keys()

        # If no active sessions, skip cleanup — could mean tmux is unavailable
        # rather than truly zero sessions. Avoids wiping all DB entries on
        # transient tmux failures (matches old returncode != 0 early return).
        if not active_sessions:
            return

        # Query database and delete orphaned entries
        db_path = get_db_path()
        with connection(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT key FROM state")
            all_keys = cursor.fetchall()

            orphaned_keys = []
            for (key,) in all_keys:
                if key not in active_sessions:
                    orphaned_keys.append(key)

            if orphaned_keys:
                placeholders = ','.join(['?'] * len(orphaned_keys))
                cursor.execute(f"DELETE FROM state WHERE key IN ({placeholders})", orphaned_keys)

    except Exception:
        pass


def startup():
    """Initialize database schema on server startup."""
    db_path = get_db_path()
    init_schema(db_path)


def run():
    """Entry point for running the MCP server."""
    startup()
    mcp.run()


if __name__ == "__main__":
    run()
