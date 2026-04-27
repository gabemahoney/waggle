"""Core async engine for waggle v2.

Caller-type agnostic — no MCP or HTTP types in signatures.
All operations return plain dicts; errors use an "error" key.
"""

import json
import shutil
import uuid
from pathlib import Path

from waggle import config, database, tmux


def _db_path() -> str:
    cfg = config.get_config()
    return str(Path(cfg["database_path"]).expanduser().absolute())


async def register_caller(
    caller_id: str,
    caller_type: str,
    cma_session_id: str | None = None,
) -> dict:
    """Register or update a caller in the database.

    Args:
        caller_id: Unique identifier for the caller.
        caller_type: Type of caller — "cma" or "local".
        cma_session_id: Optional CMA session ID (for cma callers).

    Returns:
        {"caller_id": str}
    """
    with database.connection(_db_path()) as conn:
        conn.execute(
            """
            INSERT INTO callers (caller_id, caller_type, cma_session_id)
            VALUES (?, ?, ?)
            ON CONFLICT(caller_id) DO UPDATE SET
                caller_type    = excluded.caller_type,
                cma_session_id = excluded.cma_session_id
            """,
            (caller_id, caller_type, cma_session_id),
        )

    return {"caller_id": caller_id}


async def spawn_worker(
    caller_id: str,
    model: str,
    repo: str,
    session_name: str | None = None,
    command: str | None = None,
) -> dict:
    """Spawn a new worker for the given caller.

    Flow:
    1. Count all active workers globally (status != 'done'); reject if >= max_workers
    2. Generate UUID for worker_id
    3. Generate session_name if not provided
    4. Clone/pull repo if URL
    5. Create tmux session with worker_id
    6. Launch claude with model
    7. Insert into workers table
    8. Return {worker_id, session_name}

    Args:
        caller_id: Caller performing the spawn.
        model: Claude model name (e.g. "sonnet", "haiku", "opus").
        repo: Local path or GitHub HTTPS URL.
        session_name: Optional tmux session name; generated if omitted.
        command: Optional initial command (reserved for future use).

    Returns:
        {"worker_id": str, "session_name": str}
        or {"error": str} on failure.
    """
    cfg = config.get_config()
    db_path = _db_path()
    max_workers = int(cfg["max_workers"])
    repos_path = str(Path(cfg["repos_path"]).expanduser().absolute())

    # Step 1: Global concurrency check
    with database.connection(db_path) as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM workers WHERE status != 'done'",
        ).fetchone()
        active_count = row[0] if row else 0

    if active_count >= max_workers:
        return {"error": "concurrency_limit_reached"}

    # Step 2: Worker ID
    worker_id = str(uuid.uuid4())

    # Step 3: Session name
    if not session_name:
        session_name = f"waggle-{worker_id[:8]}"

    # Step 4: Clone/pull repo
    try:
        local_repo = await tmux.clone_or_update_repo_async(repo, repos_path)
    except Exception as e:
        return {"error": f"repo_clone_failed: {e}"}

    # Step 5: Create tmux session
    session_result = await tmux.create_session(session_name, local_repo, worker_id)
    if session_result.get("status") != "success":
        return {"error": session_result.get("message", "create_session failed")}

    session_id = session_result["session_id"]

    # Step 5b: Write per-worker MCP config
    mcp_worker_port = int(cfg["mcp_worker_port"])
    worker_config_dir = Path.home() / ".waggle" / "worker-configs" / worker_id
    worker_config_dir.mkdir(parents=True, exist_ok=True)
    mcp_config_path = worker_config_dir / "mcp.json"
    mcp_config_path.write_text(
        json.dumps({
            "mcpServers": {
                "waggle-worker": {
                    "type": "http",
                    "url": f"http://localhost:{mcp_worker_port}/mcp?worker_id={worker_id}",
                }
            }
        })
    )

    # Step 6: Launch claude
    launch_result = await tmux.launch_agent_in_pane(session_id, model, mcp_config_path=str(mcp_config_path))
    if launch_result.get("status") != "success":
        await tmux.kill_session(session_id)
        shutil.rmtree(worker_config_dir, ignore_errors=True)
        return {"error": launch_result.get("message", "launch_agent_in_pane failed")}

    # Step 7: Insert into DB
    with database.connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO workers
                (worker_id, caller_id, session_name, session_id, model, repo, status)
            VALUES (?, ?, ?, ?, ?, ?, 'working')
            """,
            (worker_id, caller_id, session_name, session_id, model, repo),
        )

    return {"worker_id": worker_id, "session_name": session_name}


async def list_workers(caller_id: str) -> list[dict]:
    """List all workers for a caller.

    Args:
        caller_id: Caller whose workers to list.

    Returns:
        List of worker dicts with all worker fields.
    """
    with database.connection(_db_path()) as conn:
        rows = conn.execute(
            "SELECT * FROM workers WHERE caller_id = ?",
            (caller_id,),
        ).fetchall()

    return [dict(row) for row in rows]


async def check_status(caller_id: str, worker_id: str) -> dict:
    """Check status of a specific worker.

    Args:
        caller_id: Caller requesting status (scope check).
        worker_id: Worker to check.

    Returns:
        {"worker_id": str, "status": str, "output_lines": str,
         "updated_at": str, "pending_relay": dict | None}
        or {"error": "worker_not_found"}
    """
    db_path = _db_path()

    with database.connection(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM workers WHERE worker_id = ? AND caller_id = ?",
            (worker_id, caller_id),
        ).fetchone()

        if row is None:
            return {"error": "worker_not_found"}

        relay_row = conn.execute(
            """
            SELECT relay_id, relay_type, details
            FROM pending_relays
            WHERE worker_id = ? AND status = 'pending'
            ORDER BY created_at ASC
            LIMIT 1
            """,
            (worker_id,),
        ).fetchone()

    pending_relay = dict(relay_row) if relay_row else None

    return {
        "worker_id": row["worker_id"],
        "status": row["status"],
        "output_lines": row["output"],
        "updated_at": row["updated_at"],
        "pending_relay": pending_relay,
    }


async def get_output(caller_id: str, worker_id: str, scrollback: int = 200) -> dict:
    """Capture pane output for a worker.

    Args:
        caller_id: Caller requesting output (scope check).
        worker_id: Worker whose output to capture.
        scrollback: Number of lines to capture.

    Returns:
        {"worker_id": str, "lines": str}
        or {"error": "worker_not_found"}
    """
    with database.connection(_db_path()) as conn:
        row = conn.execute(
            "SELECT session_id FROM workers WHERE worker_id = ? AND caller_id = ?",
            (worker_id, caller_id),
        ).fetchone()

    if row is None:
        return {"error": "worker_not_found"}

    result = await tmux.capture_pane(row["session_id"], scrollback=scrollback)
    if result.get("status") != "success":
        return {"error": result.get("message", "capture_pane failed")}

    return {"worker_id": worker_id, "lines": result["content"]}


async def send_input(caller_id: str, worker_id: str, text: str) -> dict:
    """Send text input to a worker via Claude Channels notification.

    Args:
        caller_id: Caller sending the input (scope check).
        worker_id: Worker to receive the input.
        text: Text content to deliver.

    Returns:
        {"worker_id": str, "delivered": True}
        or {"error": "worker_not_found"} / {"error": "worker_not_connected"}
    """
    with database.connection(_db_path()) as conn:
        row = conn.execute(
            "SELECT worker_id FROM workers WHERE worker_id = ? AND caller_id = ?",
            (worker_id, caller_id),
        ).fetchone()

    if row is None:
        return {"error": "worker_not_found"}

    from waggle.worker_mcp import registry

    session = registry.get(worker_id)
    if session is None:
        return {"error": "worker_not_connected"}

    from mcp.types import JSONRPCNotification, JSONRPCMessage
    from mcp.shared.session import SessionMessage

    notification = JSONRPCNotification(
        jsonrpc="2.0",
        method="notifications/claude/channel",
        params={"content": text, "meta": {"worker_id": worker_id}},
    )
    session_message = SessionMessage(message=JSONRPCMessage(notification))
    await session._write_stream.send(session_message)

    return {"worker_id": worker_id, "delivered": True}


async def terminate_worker(caller_id: str, worker_id: str, force: bool = False) -> dict:
    """Terminate a worker and remove it from the database.

    Flow:
    1. Look up worker by worker_id
    2. Verify caller_id matches
    3. Kill tmux session
    4. Delete worker row from DB

    Args:
        caller_id: Caller requesting termination (scope check).
        worker_id: Worker to terminate.
        force: Currently unused; reserved for future active-worker protection.

    Returns:
        {"worker_id": str, "terminated": True}
        or {"error": "worker_not_found"}
    """
    db_path = _db_path()

    with database.connection(db_path) as conn:
        row = conn.execute(
            "SELECT session_id FROM workers WHERE worker_id = ? AND caller_id = ?",
            (worker_id, caller_id),
        ).fetchone()

    if row is None:
        return {"error": "worker_not_found"}

    await tmux.kill_session(row["session_id"])

    # Clean up per-worker MCP config directory
    worker_config_dir = Path.home() / ".waggle" / "worker-configs" / worker_id
    shutil.rmtree(worker_config_dir, ignore_errors=True)

    # Unregister from WorkerRegistry
    from waggle.worker_mcp import registry
    registry.unregister(worker_id)

    with database.connection(db_path) as conn:
        conn.execute(
            "DELETE FROM workers WHERE worker_id = ?",
            (worker_id,),
        )

    return {"worker_id": worker_id, "terminated": True}
