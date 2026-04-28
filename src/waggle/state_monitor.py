"""State monitor — polls workers table and enqueues outbound notifications on status transitions."""

import asyncio
import logging

import libtmux

from waggle import config, database
from waggle.queue import MessageEnvelope, MessageType, enqueue_outbound

logger = logging.getLogger(__name__)

_NOTIFY_STATUSES = frozenset({"ask_user", "check_permission", "done"})


async def monitor_state(outbound_queue, db_path: str, poll_interval: float = 2.0) -> None:
    """Poll workers table and enqueue outbound messages on status transitions."""
    known_statuses: dict[str, str] = {}
    cfg = config.get_config()
    output_lines = int(cfg.get("output_capture_lines", 50))

    while True:
        try:
            _poll(outbound_queue, db_path, known_statuses, output_lines)
        except Exception as e:
            logger.error("State monitor poll error: %s", e)
        await asyncio.sleep(poll_interval)


def _session_alive(session_id: str) -> bool:
    try:
        server = libtmux.Server()
        return server.sessions.get(session_id=session_id) is not None
    except Exception as e:
        logger.warning("libtmux session check failed for %s; assuming alive: %s", session_id, e)
        return True  # Assume alive if we can't check


def _poll(outbound_queue, db_path: str, known_statuses: dict, output_lines: int) -> None:
    with database.connection(db_path) as conn:
        rows = conn.execute(
            "SELECT worker_id, caller_id, session_name, session_id, status, output FROM workers"
        ).fetchall()

    for row in rows:
        worker_id = row["worker_id"]
        caller_id = row["caller_id"]
        session_name = row["session_name"]
        session_id = row["session_id"]
        current_status = row["status"]
        output = row["output"] or ""

        # Dead session detection
        if current_status != "done" and not _session_alive(session_id):
            try:
                with database.connection(db_path) as conn:
                    conn.execute(
                        "UPDATE workers SET status = 'done', updated_at = CURRENT_TIMESTAMP WHERE worker_id = ?",
                        (worker_id,),
                    )
                logger.info("Worker %s tmux session gone; marked done", worker_id)
                current_status = "done"
            except Exception as e:
                logger.error("Failed to mark dead worker %s as done: %s", worker_id, e)

        prev_status = known_statuses.get(worker_id)
        known_statuses[worker_id] = current_status

        if prev_status is None:
            # First time seeing this worker — record state, don't notify
            continue
        if current_status == prev_status:
            continue
        if current_status not in _NOTIFY_STATUSES:
            continue

        _notify_cma_callers(
            outbound_queue, db_path, worker_id, caller_id,
            session_name, current_status, output, output_lines,
        )


def _get_pending_relay(db_path: str, worker_id: str) -> dict | None:
    with database.connection(db_path) as conn:
        row = conn.execute(
            "SELECT relay_id, relay_type, details FROM pending_relays "
            "WHERE worker_id = ? AND status = 'pending' ORDER BY created_at DESC LIMIT 1",
            (worker_id,),
        ).fetchone()
    return dict(row) if row else None


def _get_cma_callers(db_path: str, caller_id: str) -> list[dict]:
    with database.connection(db_path) as conn:
        try:
            rows = conn.execute(
                "SELECT caller_id, cma_session_id FROM callers "
                "WHERE caller_id = ? AND caller_type = 'cma' AND (unreachable IS NULL OR unreachable = 0)",
                (caller_id,),
            ).fetchall()
        except Exception:
            # unreachable column not yet present (added in Task 2)
            rows = conn.execute(
                "SELECT caller_id, cma_session_id FROM callers "
                "WHERE caller_id = ? AND caller_type = 'cma'",
                (caller_id,),
            ).fetchall()
    return [dict(r) for r in rows]


def _notify_cma_callers(
    outbound_queue,
    db_path: str,
    worker_id: str,
    caller_id: str,
    session_name: str,
    status: str,
    output: str,
    output_lines: int,
) -> None:
    callers = _get_cma_callers(db_path, caller_id)
    if not callers:
        return

    captured = "\n".join(output.splitlines()[-output_lines:]) if output else ""

    pending_relay = None
    if status in ("ask_user", "check_permission"):
        try:
            pending_relay = _get_pending_relay(db_path, worker_id)
        except Exception as e:
            logger.warning("Failed to get pending relay for %s: %s", worker_id, e)

    payload = {
        "type": "worker_state_change",
        "worker_id": worker_id,
        "session_name": session_name,
        "status": status,
        "output": captured,
        "pending_relay": pending_relay,
    }

    for caller in callers:
        envelope = MessageEnvelope(
            message_type=MessageType.OUTBOUND,
            caller_id=caller["caller_id"],
            payload=payload,
        )
        try:
            enqueue_outbound(outbound_queue, envelope)
            logger.info(
                "Enqueued outbound notification: worker=%s caller=%s status=%s",
                worker_id, caller["caller_id"], status,
            )
        except Exception as e:
            logger.error("Failed to enqueue outbound for caller %s: %s", caller["caller_id"], e)
