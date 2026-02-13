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
    
    # Enrich with tmux session info (session_path) if session is still alive
    try:
        result = subprocess.run(
            ["tmux", "list-sessions", "-F", TMUX_FMT_WITH_PATH],
            capture_output=True,
            text=True,
            check=True,
            timeout=5
        )
        
        # Parse tmux output into lookup map
        tmux_sessions = {}
        for line in result.stdout.strip().split('\n'):
            if not line:
                continue
            parts = line.split(TMUX_FIELD_SEP, 3)
            if len(parts) >= 4:
                t_name, t_id, t_created, t_path = parts[0], parts[1], parts[2], parts[3]
                # Build composite key matching DB format
                composite_key = f"{t_name}+{t_id}+{t_created}"
                tmux_sessions[composite_key] = t_path
        
        # Enrich agents with tmux session_path
        for agent in agents:
            composite_key = f"{agent['name']}+{agent['session_id']}+{agent['session_created']}"
            if composite_key in tmux_sessions:
                agent["directory"] = tmux_sessions[composite_key]
                
    except subprocess.TimeoutExpired:
        # Non-fatal: agents exist in DB but we couldn't enrich with tmux data
        pass
    except subprocess.CalledProcessError:
        # Non-fatal: tmux might have no sessions, DB agents still valid
        pass
    except FileNotFoundError:
        # Non-fatal: tmux not installed, but DB agents still exist
        pass
    
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
