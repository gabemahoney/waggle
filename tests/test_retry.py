"""Tests for waggle/retry.py."""

from datetime import datetime, timedelta

import pytest

from waggle.retry import MAX_BACKOFF_SECONDS, RetryPolicy, compute_backoff, is_expired


class TestComputeBackoff:
    def test_attempt_1(self):
        assert compute_backoff(1) == 1.0

    def test_attempt_2(self):
        assert compute_backoff(2) == 2.0

    def test_attempt_3(self):
        assert compute_backoff(3) == 4.0

    def test_attempt_4(self):
        assert compute_backoff(4) == 8.0

    def test_attempt_5(self):
        assert compute_backoff(5) == 16.0

    def test_attempt_9(self):
        assert compute_backoff(9) == 256.0

    def test_attempt_10_capped(self):
        assert compute_backoff(10) == MAX_BACKOFF_SECONDS

    def test_attempt_100_capped(self):
        assert compute_backoff(100) == MAX_BACKOFF_SECONDS

    def test_max_backoff_constant(self):
        assert MAX_BACKOFF_SECONDS == 300


class TestIsExpired:
    def test_none_first_attempted_returns_false(self):
        assert is_expired(None, max_retry_hours=72) is False

    def test_recent_time_returns_false(self):
        recent = datetime.now() - timedelta(hours=1)
        assert is_expired(recent, max_retry_hours=72) is False

    def test_expired_time_returns_true(self):
        old = datetime.now() - timedelta(hours=73)
        assert is_expired(old, max_retry_hours=72) is True

    def test_exactly_at_boundary_not_expired(self):
        # Just inside the deadline
        just_inside = datetime.now() - timedelta(hours=71, minutes=59)
        assert is_expired(just_inside, max_retry_hours=72) is False

    def test_custom_max_retry_hours(self):
        two_hours_ago = datetime.now() - timedelta(hours=2, minutes=1)
        assert is_expired(two_hours_ago, max_retry_hours=2) is True

    def test_custom_max_retry_hours_not_expired(self):
        one_hour_ago = datetime.now() - timedelta(hours=1)
        assert is_expired(one_hour_ago, max_retry_hours=2) is False


class TestRetryPolicy:
    def test_default_values(self):
        policy = RetryPolicy()
        assert policy.admin_notify_after_retries == 5
        assert policy.max_retry_hours == 72

    def test_custom_values(self):
        policy = RetryPolicy(admin_notify_after_retries=3, max_retry_hours=24)
        assert policy.admin_notify_after_retries == 3
        assert policy.max_retry_hours == 24

    def test_partial_custom(self):
        policy = RetryPolicy(admin_notify_after_retries=10)
        assert policy.admin_notify_after_retries == 10
        assert policy.max_retry_hours == 72
