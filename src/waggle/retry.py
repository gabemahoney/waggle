"""Retry policy for outbound CMA notifications."""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

MAX_BACKOFF_SECONDS = 300  # 5 minutes cap


@dataclass
class RetryPolicy:
    admin_notify_after_retries: int = 5
    max_retry_hours: int = 72


def compute_backoff(attempt_count: int) -> float:
    """Compute exponential backoff: min(1 * 2^(n-1), 300) seconds."""
    return min(1.0 * (2 ** (attempt_count - 1)), MAX_BACKOFF_SECONDS)


def is_expired(first_attempted_at: datetime | None, max_retry_hours: int) -> bool:
    """Return True if max retry duration has been exceeded."""
    if first_attempted_at is None:
        return False
    deadline = first_attempted_at + timedelta(hours=max_retry_hours)
    return datetime.now() > deadline
