"""MCP Server for Waggle Agent State Management.

Provides FastMCP server initialization with database integration.
"""

from pathlib import Path
from typing import Optional
from urllib.parse import urlparse, unquote
from fastmcp import FastMCP, Context
from fastmcp.exceptions import NotFoundError
from mcp.shared.exceptions import McpError

from waggle.config import get_db_path
from waggle.database import init_schema, connection
from waggle.tmux import (
    get_sessions,
    get_active_session_keys,
    kill_session,
    validate_session_name_id,
    check_llm_running,
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
        return {"status": "error", "message": f"Failed to query database: {str(e)}"}

    if matching_key is None:
        return {"status": "error", "message": f"Session '{session_id}' not found in database"}

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
