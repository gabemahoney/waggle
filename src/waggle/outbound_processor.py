"""Outbound queue processor — delivers CMA push notifications."""

import asyncio
import json
import logging
from datetime import datetime

from waggle import config, database
from waggle.cma_client import CMAClient, CMARetryableError, CMATerminalError
from waggle.mailer import build_escalation_body, send_admin_email
from waggle.queue import MessageEnvelope, enqueue_outbound
from waggle.retry import RetryPolicy, compute_backoff, is_expired

logger = logging.getLogger(__name__)


def _mark_caller_unreachable(db_path: str, caller_id: str) -> None:
    with database.connection(db_path) as conn:
        conn.execute(
            "UPDATE callers SET unreachable = 1 WHERE caller_id = ?",
            (caller_id,),
        )


async def process_outbound(queue, cma_client: CMAClient | None, db_path: str) -> None:
    """Continuously process outbound queue messages."""
    cfg = config.get_config()
    policy = RetryPolicy(
        admin_notify_after_retries=cfg["admin_notify_after_retries"],
        max_retry_hours=cfg["max_retry_hours"],
    )
    admin_email = cfg["admin_email"]

    while True:
        try:
            raw = queue.get(block=False)
        except Exception:
            await asyncio.sleep(0.1)
            continue

        envelope = None
        try:
            envelope = MessageEnvelope.from_dict(json.loads(raw))

            if envelope.first_attempted_at is None:
                envelope.first_attempted_at = datetime.now()
            envelope.attempt_count += 1

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
            if envelope:
                try:
                    _mark_caller_unreachable(db_path, envelope.caller_id)
                except Exception as db_err:
                    logger.error("Failed to mark caller %s unreachable: %s", envelope.caller_id, db_err)
                try:
                    body = build_escalation_body(
                        worker_id=envelope.payload.get("worker_id", ""),
                        session_name=envelope.payload.get("session_name", ""),
                        caller_id=envelope.caller_id,
                        error_type="terminal",
                        status_code=e.status_code,
                        attempt_count=envelope.attempt_count,
                        first_failure=envelope.first_attempted_at.isoformat() if envelope.first_attempted_at else "",
                    )
                    send_admin_email(
                        admin_email,
                        f"[waggle] CMA terminal error for {envelope.caller_id}",
                        body,
                    )
                except Exception as mail_err:
                    logger.error("Failed to send terminal escalation email: %s", mail_err)

        except CMARetryableError as e:
            caller = envelope.caller_id if envelope else "?"
            if envelope and is_expired(envelope.first_attempted_at, policy.max_retry_hours):
                logger.error("CMA max retry duration exceeded for caller %s; dropping", caller)
                try:
                    queue.ack(raw)
                except Exception:
                    pass
                try:
                    body = build_escalation_body(
                        worker_id=envelope.payload.get("worker_id", ""),
                        session_name=envelope.payload.get("session_name", ""),
                        caller_id=envelope.caller_id,
                        error_type="retryable_expired",
                        status_code=e.status_code,
                        attempt_count=envelope.attempt_count,
                        first_failure=envelope.first_attempted_at.isoformat() if envelope.first_attempted_at else "",
                    )
                    send_admin_email(
                        admin_email,
                        f"[waggle] CMA max retries exceeded for {envelope.caller_id}",
                        body,
                    )
                except Exception as mail_err:
                    logger.error("Failed to send expiry escalation email: %s", mail_err)
            else:
                attempt = envelope.attempt_count if envelope else 1
                backoff = compute_backoff(attempt)
                logger.warning(
                    "CMA retryable error for caller %s; retrying in %.1fs (attempt %d): %s",
                    caller, backoff, attempt, e,
                )
                await asyncio.sleep(backoff)
                try:
                    queue.ack(raw)
                    if envelope:
                        enqueue_outbound(queue, envelope)
                except Exception:
                    pass
                if envelope and envelope.attempt_count == policy.admin_notify_after_retries:
                    try:
                        body = build_escalation_body(
                            worker_id=envelope.payload.get("worker_id", ""),
                            session_name=envelope.payload.get("session_name", ""),
                            caller_id=envelope.caller_id,
                            error_type="retryable",
                            status_code=e.status_code,
                            attempt_count=envelope.attempt_count,
                            first_failure=envelope.first_attempted_at.isoformat() if envelope.first_attempted_at else "",
                        )
                        send_admin_email(
                            admin_email,
                            f"[waggle] CMA delivery failing for {envelope.caller_id}",
                            body,
                        )
                    except Exception as mail_err:
                        logger.error("Failed to send retry threshold escalation email: %s", mail_err)

        except Exception as e:
            logger.error("Outbound processing error: %s", e)
            try:
                queue.nack(raw)
            except Exception:
                pass
