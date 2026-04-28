"""Inbound queue processor — dequeues REST async mutations and dispatches to engine."""

import asyncio
import json
import logging

from waggle import config, database, engine
from waggle.queue import MessageEnvelope

logger = logging.getLogger(__name__)


async def process_inbound(queue) -> None:
    """Continuously process inbound queue messages."""
    db_path = config.get_db_path()

    while True:
        try:
            raw = queue.get(block=False)
        except Exception:
            await asyncio.sleep(0.1)
            continue

        try:
            envelope = MessageEnvelope.from_dict(json.loads(raw))
            payload = envelope.payload
            operation = payload.get("operation")
            request_id = payload.get("request_id")
            caller_id = envelope.caller_id

            if operation == "spawn_worker":
                result = await engine.spawn_worker(
                    caller_id,
                    payload["model"],
                    payload["repo"],
                    payload.get("session_name"),
                    payload.get("command"),
                )
            elif operation == "send_input":
                result = await engine.send_input(
                    caller_id,
                    payload["worker_id"],
                    payload["text"],
                )
            elif operation == "terminate_worker":
                result = await engine.terminate_worker(
                    caller_id,
                    payload["worker_id"],
                )
            else:
                result = {"error": f"unknown_operation: {operation}"}

            if "error" in result:
                database.fail_request(db_path, request_id, json.dumps(result))
            else:
                database.complete_request(db_path, request_id, json.dumps(result))

            queue.ack(raw)
            logger.info("Processed inbound %s: %s", operation, request_id)

        except Exception as e:
            logger.error("Inbound processing error: %s", e)
            try:
                queue.nack(raw)
            except Exception:
                pass
