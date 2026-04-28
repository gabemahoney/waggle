"""Integration tests: state_monitor → outbound queue → CMAClient delivery."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import pytest_asyncio

from waggle.cma_client import CMAClient, CMARetryableError, CMATerminalError
from waggle.database import connection, init_schema
from waggle.outbound_processor import _mark_caller_unreachable, process_outbound
from waggle.queue import MessageEnvelope, MessageType, enqueue_outbound, get_outbound_queue
from waggle.state_monitor import _poll


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _setup_db(db_path):
    init_schema(db_path)
    with connection(db_path) as conn:
        conn.execute(
            "INSERT INTO callers (caller_id, caller_type, cma_session_id, unreachable)"
            " VALUES (?, ?, ?, ?)",
            ("c1", "cma", "cma-session-abc", 0),
        )
        conn.execute(
            "INSERT INTO workers (worker_id, caller_id, session_name, session_id, model, repo, status)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("w1", "c1", "my-worker", "tmux-1", "claude-sonnet", "/repo", "done"),
        )


class _StopLoop(Exception):
    """Breaks infinite processor loops."""


def _make_queue_with_one_item(tmp_path):
    """Create a real persist-queue with one item from _poll."""
    queue_path = str(tmp_path / "q.db")
    return get_outbound_queue(queue_path)


# ---------------------------------------------------------------------------
# Happy path: done notification delivered to mock CMA endpoint
# ---------------------------------------------------------------------------


class TestIntegrationHappyPath:
    @pytest.mark.asyncio
    async def test_done_notification_delivered(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        _setup_db(db_path)

        q = _make_queue_with_one_item(tmp_path)
        known = {"w1": "working"}  # previous status

        # Step 1: _poll enqueues a notification
        with patch("waggle.state_monitor._session_alive", return_value=True):
            _poll(q, db_path, known, output_lines=50)

        assert q.size == 1

        # Step 2: dequeue and verify contents
        raw = q.get(block=False)
        data = json.loads(raw)
        assert data["caller_id"] == "c1"
        assert data["payload"]["status"] == "done"
        assert data["payload"]["worker_id"] == "w1"
        q.ack(raw)

        # Step 3: deliver via CMAClient with MockTransport
        response_body = json.dumps({"ok": True})

        def mock_handler(request):
            assert "/v1/sessions/cma-session-abc/events" in str(request.url)
            return httpx.Response(200, text=response_body)

        transport = httpx.MockTransport(mock_handler)
        async with httpx.AsyncClient(transport=transport, base_url="https://api.anthropic.com") as http_client:
            client = CMAClient.__new__(CMAClient)
            client._client = http_client

            await client.send_worker_event(
                cma_session_id="cma-session-abc",
                worker_id="w1",
                session_name="my-worker",
                status="done",
                output="",
                pending_relay=None,
            )

        q.close()

    @pytest.mark.asyncio
    async def test_poll_then_process_outbound_full_flow(self, tmp_path):
        """Full flow: _poll enqueues → process_outbound dequeues + calls CMAClient."""
        db_path = str(tmp_path / "test.db")
        _setup_db(db_path)

        q = _make_queue_with_one_item(tmp_path)
        known = {"w1": "working"}

        with patch("waggle.state_monitor._session_alive", return_value=True):
            _poll(q, db_path, known, output_lines=50)

        assert q.size == 1

        # Mock CMAClient.send_worker_event
        mock_send = AsyncMock()
        mock_client = MagicMock(spec=CMAClient)
        mock_client.send_worker_event = mock_send

        call_count = 0
        original_get = q.get

        def get_once(block=True):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return original_get(block=False)
            raise Exception("empty")

        q.get = get_once

        with patch("waggle.config.get_config", return_value={
            "admin_notify_after_retries": 5,
            "max_retry_hours": 72,
            "admin_email": "admin@example.com",
        }):
            with patch("asyncio.sleep", new=AsyncMock(side_effect=_StopLoop)):
                try:
                    await process_outbound(q, mock_client, db_path)
                except _StopLoop:
                    pass

        mock_send.assert_called_once()
        call_kwargs = mock_send.call_args.kwargs
        assert call_kwargs["cma_session_id"] == "cma-session-abc"
        assert call_kwargs["status"] == "done"
        assert call_kwargs["worker_id"] == "w1"

        q.close()


# ---------------------------------------------------------------------------
# 500 retryable: message stays for retry (nack behavior)
# ---------------------------------------------------------------------------


class TestIntegration500Retryable:
    @pytest.mark.asyncio
    async def test_500_causes_ack_and_reenqueue(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        _setup_db(db_path)

        q = _make_queue_with_one_item(tmp_path)
        known = {"w1": "working"}

        with patch("waggle.state_monitor._session_alive", return_value=True):
            _poll(q, db_path, known, output_lines=50)

        assert q.size == 1

        mock_client = MagicMock(spec=CMAClient)
        mock_client.send_worker_event = AsyncMock(
            side_effect=CMARetryableError(500, "server error")
        )

        call_count = 0
        original_get = q.get

        def get_once(block=True):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return original_get(block=False)
            raise Exception("empty")

        q.get = get_once

        # The processor does: CMARetryableError → sleep(backoff) → ack → reenqueue → get(empty) → sleep(0.1)
        # We let the first sleep (backoff) pass through, then stop on the second (empty-queue) sleep.
        sleep_count = 0

        async def controlled_sleep(t):
            nonlocal sleep_count
            sleep_count += 1
            if sleep_count >= 2:
                raise _StopLoop()

        with patch("waggle.config.get_config", return_value={
            "admin_notify_after_retries": 5,
            "max_retry_hours": 72,
            "admin_email": "admin@example.com",
        }):
            with patch("asyncio.sleep", new=controlled_sleep):
                try:
                    await process_outbound(q, mock_client, db_path)
                except _StopLoop:
                    pass

        # Restore real get before asserting
        q.get = original_get

        # Message was acked (removed from in-flight) and re-enqueued
        assert q.size == 1
        raw = q.get(block=False)
        data = json.loads(raw)
        assert data["attempt_count"] == 1
        q.ack(raw)
        q.close()


# ---------------------------------------------------------------------------
# 404 terminal: ack + mark caller unreachable + email sent
# ---------------------------------------------------------------------------


class TestIntegration404Terminal:
    @pytest.mark.asyncio
    async def test_404_marks_caller_unreachable_and_sends_email(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        _setup_db(db_path)

        q = _make_queue_with_one_item(tmp_path)
        known = {"w1": "working"}

        with patch("waggle.state_monitor._session_alive", return_value=True):
            _poll(q, db_path, known, output_lines=50)

        assert q.size == 1

        mock_client = MagicMock(spec=CMAClient)
        mock_client.send_worker_event = AsyncMock(
            side_effect=CMATerminalError(404, "not found")
        )

        call_count = 0
        original_get = q.get

        def get_once(block=True):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return original_get(block=False)
            raise Exception("empty")

        q.get = get_once

        with patch("waggle.config.get_config", return_value={
            "admin_notify_after_retries": 5,
            "max_retry_hours": 72,
            "admin_email": "admin@example.com",
        }):
            with patch("waggle.outbound_processor.send_admin_email") as mock_mail:
                with patch("asyncio.sleep", new=AsyncMock(side_effect=_StopLoop)):
                    try:
                        await process_outbound(q, mock_client, db_path)
                    except _StopLoop:
                        pass

        # Queue should be empty (acked, not re-enqueued)
        assert q.size == 0

        # Caller should be marked unreachable
        with connection(db_path) as conn:
            row = conn.execute(
                "SELECT unreachable FROM callers WHERE caller_id = ?", ("c1",)
            ).fetchone()
        assert row["unreachable"] == 1

        # Admin email should have been sent
        mock_mail.assert_called_once()
        subject = mock_mail.call_args[0][1]
        assert "terminal" in subject.lower() or "c1" in subject

        q.close()


# ---------------------------------------------------------------------------
# _mark_caller_unreachable (unit test)
# ---------------------------------------------------------------------------


class TestMarkCallerUnreachable:
    def test_sets_unreachable_flag(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        init_schema(db_path)
        with connection(db_path) as conn:
            conn.execute(
                "INSERT INTO callers (caller_id, caller_type, unreachable) VALUES (?, ?, ?)",
                ("c-test", "cma", 0),
            )

        _mark_caller_unreachable(db_path, "c-test")

        with connection(db_path) as conn:
            row = conn.execute(
                "SELECT unreachable FROM callers WHERE caller_id = ?", ("c-test",)
            ).fetchone()
        assert row["unreachable"] == 1
