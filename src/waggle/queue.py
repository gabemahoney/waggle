"""Durable message queue for waggle v2 async operations."""

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from uuid import uuid4

from persistqueue import SQLiteAckQueue


class MessageType(str, Enum):
    INBOUND = "INBOUND"
    OUTBOUND = "OUTBOUND"


@dataclass
class MessageEnvelope:
    message_type: MessageType
    caller_id: str
    payload: dict
    envelope_id: str = field(default_factory=lambda: str(uuid4()))
    attempt_count: int = 0
    first_attempted_at: datetime | None = None

    def to_dict(self) -> dict:
        return {
            "message_type": self.message_type.value,
            "caller_id": self.caller_id,
            "payload": self.payload,
            "envelope_id": self.envelope_id,
            "attempt_count": self.attempt_count,
            "first_attempted_at": self.first_attempted_at.isoformat() if self.first_attempted_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MessageEnvelope":
        return cls(
            message_type=MessageType(data["message_type"]),
            caller_id=data["caller_id"],
            payload=data["payload"],
            envelope_id=data["envelope_id"],
            attempt_count=data.get("attempt_count", 0),
            first_attempted_at=datetime.fromisoformat(data["first_attempted_at"]) if data.get("first_attempted_at") else None,
        )


def get_inbound_queue(queue_path: str) -> SQLiteAckQueue:
    """Get or create the inbound durable queue."""
    path = Path(queue_path).parent / "inbound"
    path.mkdir(parents=True, exist_ok=True)
    return SQLiteAckQueue(str(path), multithreading=True)


def get_outbound_queue(queue_path: str) -> SQLiteAckQueue:
    """Get or create the outbound durable queue."""
    path = Path(queue_path).parent / "outbound"
    path.mkdir(parents=True, exist_ok=True)
    return SQLiteAckQueue(str(path), multithreading=True)


def enqueue_inbound(queue: SQLiteAckQueue, envelope: MessageEnvelope) -> None:
    """Enqueue a message to the inbound queue."""
    queue.put(json.dumps(envelope.to_dict()))


def enqueue_outbound(queue: SQLiteAckQueue, envelope: MessageEnvelope) -> None:
    """Enqueue a message to the outbound queue."""
    queue.put(json.dumps(envelope.to_dict()))
