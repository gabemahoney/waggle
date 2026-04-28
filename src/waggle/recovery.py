"""Restart recovery — rediscover workers, reconnect MCP, drain queues."""

import asyncio
import logging
from pathlib import Path

import libtmux

from waggle import database
from waggle.queue import MessageEnvelope, MessageType, enqueue_outbound
from waggle.state_monitor import _session_alive

logger = logging.getLogger(__name__)


async def restart_recovery(outbound_queue, db_path: str) -> dict:
    """Run restart recovery at daemon startup.

    Returns dict with counts: {"alive": N, "dead": N, "relays_timed_out": N}
    """
    result = {"alive": 0, "dead": 0, "relays_timed_out": 0}

    # 1. Load non-done workers from DB
    with database.connection(db_path) as conn:
        rows = conn.execute(
            "SELECT worker_id, caller_id, session_name, session_id, status FROM workers WHERE status != 'done'"
        ).fetchall()

    for row in rows:
        worker_id = row["worker_id"]
        session_id = row["session_id"]
        session_name = row["session_name"]
        caller_id = row["caller_id"]

        if _session_alive(session_id):
            # Alive: send MCP reconnect, add to monitoring
            result["alive"] += 1
            await _send_mcp_reconnect(session_id)
            logger.info("Recovery: worker %s alive, MCP reconnect sent", worker_id)
        else:
            # Dead: mark done, notify CMA, timeout pending relays
            result["dead"] += 1
            with database.connection(db_path) as conn:
                conn.execute(
                    "UPDATE workers SET status = 'done', updated_at = CURRENT_TIMESTAMP WHERE worker_id = ?",
                    (worker_id,),
                )
            logger.info("Recovery: worker %s dead, marked done", worker_id)

            # Enqueue CMA notification for dead worker
            _enqueue_dead_notification(outbound_queue, worker_id, session_name, caller_id)

            # Timeout pending relays for dead workers
            timed_out = _timeout_pending_relays(db_path, worker_id)
            result["relays_timed_out"] += timed_out

    # 2. Leave pending relays for alive workers as-is (hooks still polling)

    # 3. Drain unacked queue messages (persist-queue handles this — just log)
    # SQLiteAckQueue automatically makes unacked messages available on restart
    # No explicit drain needed — they'll be picked up by the processors
    logger.info("Recovery: queues ready for processing (unacked messages available)")

    # 4. Enforce file permissions
    _enforce_permissions()

    logger.info(
        "Recovery complete: %d alive, %d dead, %d relays timed out",
        result["alive"], result["dead"], result["relays_timed_out"],
    )
    return result


def _send_mcp_reconnect_sync(session_id: str) -> None:
    """Send /mcp reconnect waggle-worker to a tmux session."""
    try:
        server = libtmux.Server()
        session = server.sessions.get(session_id=session_id)
        if session is None:
            return
        pane = session.active_window.active_pane
        pane.send_keys("/mcp reconnect waggle-worker", enter=True)
    except Exception as e:
        logger.warning("Failed to send MCP reconnect to %s: %s", session_id, e)


async def _send_mcp_reconnect(session_id: str) -> None:
    """Async wrapper for MCP reconnect."""
    await asyncio.to_thread(_send_mcp_reconnect_sync, session_id)


def _enqueue_dead_notification(outbound_queue, worker_id: str, session_name: str, caller_id: str) -> None:
    """Enqueue outbound CMA notification for a dead worker."""
    payload = {
        "type": "worker_state_change",
        "worker_id": worker_id,
        "session_name": session_name,
        "status": "done",
        "output": "(worker tmux session lost during daemon restart)",
        "pending_relay": None,
    }
    envelope = MessageEnvelope(
        message_type=MessageType.OUTBOUND,
        caller_id=caller_id,
        payload=payload,
    )
    try:
        enqueue_outbound(outbound_queue, envelope)
    except Exception as e:
        logger.error("Failed to enqueue dead worker notification for %s: %s", worker_id, e)


def _timeout_pending_relays(db_path: str, worker_id: str) -> int:
    """Mark all pending relays for a worker as timed out. Returns count."""
    with database.connection(db_path) as conn:
        cursor = conn.execute(
            "UPDATE pending_relays SET status = 'timeout', resolved_at = CURRENT_TIMESTAMP "
            "WHERE worker_id = ? AND status = 'pending'",
            (worker_id,),
        )
        return cursor.rowcount


def _enforce_permissions() -> None:
    """Enforce file permissions on ~/.waggle/ directory."""
    waggle_dir = Path.home() / ".waggle"
    if not waggle_dir.exists():
        waggle_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        return

    try:
        # Directory: 0o700
        waggle_dir.chmod(0o700)

        # Files: 0o600
        for item in waggle_dir.iterdir():
            if item.is_file():
                item.chmod(0o600)
            elif item.is_dir():
                item.chmod(0o700)
    except OSError as e:
        logger.warning("Failed to enforce permissions on ~/.waggle/: %s", e)
