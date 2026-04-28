"""Outbound queue processor — delivers CMA push notifications."""

import asyncio
import json
import logging

from waggle import database
from waggle.cma_client import CMAClient, CMARetryableError, CMATerminalError
from waggle.queue import MessageEnvelope

logger = logging.getLogger(__name__)


async def process_outbound(queue, cma_client: CMAClient | None, db_path: str) -> None:
    """Continuously process outbound queue messages."""
    while True:
        try:
            raw = queue.get(block=False)
        except Exception:
            await asyncio.sleep(0.1)
            continue

        envelope = None
        try:
            envelope = MessageEnvelope.from_dict(json.loads(raw))
            payload = envelope.payload

            if cma_client is None:
                logger.debug("No CMA client configured; dropping outbound for %s", envelope.caller_id)
                queue.ack(raw)
                continue

            with database.connection(db_path) as conn:
                row = conn.execute(
                    "SELECT cma_session_id FROM callers WHERE caller_id = ?",
                    (envelope.caller_id,),
                ).fetchone()

            if row is None or not row["cma_session_id"]:
                logger.warning("No cma_session_id for caller %s; dropping", envelope.caller_id)
                queue.ack(raw)
                continue

            await cma_client.send_worker_event(
                cma_session_id=row["cma_session_id"],
                worker_id=payload.get("worker_id", ""),
                session_name=payload.get("session_name", ""),
                status=payload.get("status", ""),
                output=payload.get("output", ""),
                pending_relay=payload.get("pending_relay"),
            )
            queue.ack(raw)
            logger.info(
                "Delivered CMA notification: worker=%s caller=%s",
                payload.get("worker_id"), envelope.caller_id,
            )

        except CMATerminalError as e:
            caller = envelope.caller_id if envelope else "?"
            logger.error("CMA terminal error for caller %s; dropping: %s", caller, e)
            try:
                queue.ack(raw)
            except Exception:
                pass
        except CMARetryableError as e:
            logger.warning("CMA retryable error; nacking for retry: %s", e)
            try:
                queue.nack(raw)
            except Exception:
                pass
        except Exception as e:
            logger.error("Outbound processing error: %s", e)
            try:
                queue.nack(raw)
            except Exception:
                pass
