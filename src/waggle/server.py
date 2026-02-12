"""MCP Server for Waggle Agent State Management.

Provides FastMCP server initialization with database integration.
"""

import subprocess
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse, unquote
from fastmcp import FastMCP, Context
from fastmcp.exceptions import NotFoundError
from mcp.shared.exceptions import McpError

from waggle.config import get_db_path
from waggle.database import init_schema, connection

# Delimiter for tmux format string output. Tab is used instead of colon
# because tmux session names can contain colons, which would break parsing.
TMUX_FIELD_SEP = "\t"

# tmux format strings for list-sessions queries
# 4-field variant: used by list_agents (includes session_path)
TMUX_FMT_WITH_PATH = TMUX_FIELD_SEP.join([
    "#{session_name}", "#{session_id}", "#{session_created}", "#{session_path}"
])
# 3-field variant: used by cleanup_dead_sessions (no path needed)
TMUX_FMT_KEYS_ONLY = TMUX_FIELD_SEP.join([
    "#{session_name}", "#{session_id}", "#{session_created}"
])

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
    Returns all agents system-wide with optional filtering by repository path.## Output Formatting

    When responding to user, use this structured format example (but replace with returned values

    ┌───────────────────┬─────────┬────────────────────┬────┐
    │ Name              │ Status  │ Directory          │ ID │
    ├───────────────────┼─────────┼────────────────────┼────┤
    │ agent-abc123      │ working │ /path/to/project1  │ $1 │
    ├───────────────────┼─────────┼────────────────────┼────┤
    │ agent-def456      │ waiting │ /path/to/project2  │ $2 │
    └───────────────────┴─────────┴────────────────────┴────┘

    If the directory value seem too long (~30 chars or so ) then truncate from the front, not the back e.g .../projects/project1 not /Users/user/projects/...

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

    # Query tmux sessions
    try:
        result = subprocess.run(
            ["tmux", "list-sessions", "-F", TMUX_FMT_WITH_PATH],
            capture_output=True,
            text=True,
            check=True,
            timeout=5
        )
    except subprocess.TimeoutExpired:
        return {
            "status": "error",
            "error": "tmux command timed out after 5 seconds"
        }
    except subprocess.CalledProcessError as e:
        # tmux returns non-zero if no sessions exist
        if "no server running" in e.stderr.lower() or "no sessions" in e.stderr.lower():
            return {"status": "success", "agents": []}
        return {
            "status": "error",
            "error": f"Failed to query tmux sessions: {e.stderr.strip()}"
        }
    except FileNotFoundError:
        return {
            "status": "error",
            "error": "tmux command not found - is tmux installed?"
        }
    
    # Parse tmux output into session objects
    sessions = []
    for line in result.stdout.strip().split('\n'):
        if not line:
            continue
        parts = line.split(TMUX_FIELD_SEP, 3)  # Split into max 4 parts
        if len(parts) >= 4:
            session_name, session_id, session_created, session_path = parts[0], parts[1], parts[2], parts[3]
            # Apply name filter if provided
            if name is None or session_name == name:
                sessions.append({
                    "name": session_name,
                    "session_id": session_id,
                    "session_created": session_created,
                    "directory": session_path,
                    "status": "unknown"  # Default status
                })
    
    # Query database for agent state
    db_path = get_db_path()
    try:
        with connection(db_path) as conn:
            cursor = conn.cursor()
            # Query all state entries
            cursor.execute("SELECT key, repo, status FROM state")
            state_entries = cursor.fetchall()
            
            # Build a lookup map: composite_key -> (repo, status)
            # Composite key: name+session_id+session_created
            state_map = {}
            for key, repo_path, status in state_entries:
                # Key format: name+session_id+session_created (no namespace prefix)
                # Status: Custom state string (any value set by agents, e.g. "working", "waiting_for_input", etc.)
                state_map[key] = (repo_path, status)

            # Update session statuses and repos based on database state
            for session in sessions:
                # Build composite key for this session
                composite_key = f"{session['name']}+{session['session_id']}+{session['session_created']}"
                if composite_key in state_map:
                    repo_path, status = state_map[composite_key]
                    session["status"] = status
                    session["repo"] = repo_path
                else:
                    session["repo"] = None
                    
    except Exception as e:
        return {
            "status": "error",
            "error": f"Failed to query database: {str(e)}"
        }
    
    # Filter by repository if repo parameter provided
    if repo is not None:
        repo_lower = repo.lower()
        sessions = [
            session for session in sessions
            if session.get("repo") is not None and repo_lower in session["repo"].lower()
        ]
    
    return {
        "status": "success",
        "agents": sessions
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


def cleanup_dead_sessions():
    """Remove database entries for dead tmux sessions.
    
    Queries tmux for active sessions and removes database entries for sessions
    that no longer exist. Can be called synchronously (cleanup happens in-place).
    Silently handles all errors - never raises exceptions.
    """
    try:
        # Get active tmux sessions
        result = subprocess.run(
            ["tmux", "list-sessions", "-F", TMUX_FMT_KEYS_ONLY],
            capture_output=True,
            text=True,
            timeout=2
        )
        
        # If tmux fails (no server, no sessions, etc), skip cleanup
        if result.returncode != 0:
            return
        
        # Parse active sessions into set of composite keys
        active_sessions = set()
        for line in result.stdout.strip().split('\n'):
            if line:
                parts = line.split(TMUX_FIELD_SEP, 2)
                if len(parts) >= 3:
                    name, session_id, session_created = parts[0], parts[1], parts[2]
                    composite_key = f"{name}+{session_id}+{session_created}"
                    active_sessions.add(composite_key)
        
        # Query database and delete orphaned entries
        db_path = get_db_path()
        with connection(db_path) as conn:
            cursor = conn.cursor()
            
            # Get all state entries
            cursor.execute("SELECT key FROM state")
            all_keys = cursor.fetchall()
            
            # Find orphaned entries
            orphaned_keys = []
            for (key,) in all_keys:
                # Key format: name+session_id+session_created (no namespace prefix)
                if key not in active_sessions:
                    # Session is dead, collect for batch deletion
                    orphaned_keys.append(key)
            
            # Batch delete all orphaned entries in a single statement
            if orphaned_keys:
                placeholders = ','.join(['?'] * len(orphaned_keys))
                # Note: f-string is used only for placeholder generation (?), not data interpolation
                cursor.execute(f"DELETE FROM state WHERE key IN ({placeholders})", orphaned_keys)
            
    except Exception:
        # Silent failure - all errors ignored
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
