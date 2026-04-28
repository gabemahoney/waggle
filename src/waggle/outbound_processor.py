"""Outbound queue processor — stub for CMA notification delivery (Epic 6)."""

import asyncio
import json
import logging

from waggle.queue import MessageEnvelope

logger = logging.getLogger(__name__)


async def process_outbound(queue) -> None:
    """Continuously process outbound queue messages (stub)."""
    while True:
        try:
            raw = queue.get(block=False)
        except Exception:
            await asyncio.sleep(0.1)
            continue

        try:
            envelope = MessageEnvelope.from_dict(json.loads(raw))
            logger.info(
                "Outbound stub: would deliver %s to %s",
                envelope.payload.get("type", "unknown"),
                envelope.caller_id,
            )
            queue.ack(raw)
        except Exception as e:
            logger.error("Outbound processing error: %s", e)
            try:
                queue.nack(raw)
            except Exception:
                pass
