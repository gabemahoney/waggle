"""Tests for queue.py, inbound_processor.py, and outbound_processor.py."""

import asyncio
import json
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from waggle.queue import (
    MessageEnvelope,
    MessageType,
    enqueue_inbound,
    enqueue_outbound,
    get_inbound_queue,
    get_outbound_queue,
)


# ---------------------------------------------------------------------------
# MessageEnvelope
# ---------------------------------------------------------------------------


class TestMessageEnvelopeRoundtrip:
    def test_basic_roundtrip(self):
        env = MessageEnvelope(
            message_type=MessageType.INBOUND,
            caller_id="caller-1",
            payload={"operation": "spawn_worker", "model": "sonnet"},
        )
        restored = MessageEnvelope.from_dict(env.to_dict())
        assert restored.message_type == MessageType.INBOUND
        assert restored.caller_id == "caller-1"
        assert restored.payload == {"operation": "spawn_worker", "model": "sonnet"}
        assert restored.envelope_id == env.envelope_id
        assert restored.attempt_count == 0
        assert restored.first_attempted_at is None

    def test_roundtrip_with_timestamp(self):
        now = datetime(2025, 1, 15, 12, 0, 0)
        env = MessageEnvelope(
            message_type=MessageType.OUTBOUND,
            caller_id="caller-2",
            payload={"type": "status"},
            attempt_count=3,
            first_attempted_at=now,
        )
        restored = MessageEnvelope.from_dict(env.to_dict())
        assert restored.message_type == MessageType.OUTBOUND
        assert restored.attempt_count == 3
        assert restored.first_attempted_at == now

    def test_envelope_id_auto_generated(self):
        e1 = MessageEnvelope(message_type=MessageType.INBOUND, caller_id="c", payload={})
        e2 = MessageEnvelope(message_type=MessageType.INBOUND, caller_id="c", payload={})
        assert e1.envelope_id != e2.envelope_id


class TestMessageTypeEnum:
    def test_inbound_value(self):
        assert MessageType.INBOUND == "INBOUND"
        assert MessageType.INBOUND.value == "INBOUND"

    def test_outbound_value(self):
        assert MessageType.OUTBOUND == "OUTBOUND"
        assert MessageType.OUTBOUND.value == "OUTBOUND"

    def test_is_str_subclass(self):
        assert isinstance(MessageType.INBOUND, str)


# ---------------------------------------------------------------------------
# Queue creation
# ---------------------------------------------------------------------------


class TestGetInboundQueue:
    def test_creates_inbound_subdir(self, tmp_path):
        queue_path = str(tmp_path / "queue.db")
        q = get_inbound_queue(queue_path)
        assert (tmp_path / "inbound").is_dir()
        q.close()

    def test_returns_ack_queue(self, tmp_path):
        from persistqueue import SQLiteAckQueue
        queue_path = str(tmp_path / "queue.db")
        q = get_inbound_queue(queue_path)
        assert isinstance(q, SQLiteAckQueue)
        q.close()


class TestGetOutboundQueue:
    def test_creates_outbound_subdir(self, tmp_path):
        queue_path = str(tmp_path / "queue.db")
        q = get_outbound_queue(queue_path)
        assert (tmp_path / "outbound").is_dir()
        q.close()

    def test_returns_ack_queue(self, tmp_path):
        from persistqueue import SQLiteAckQueue
        queue_path = str(tmp_path / "queue.db")
        q = get_outbound_queue(queue_path)
        assert isinstance(q, SQLiteAckQueue)
        q.close()


# ---------------------------------------------------------------------------
# Enqueue / dequeue
# ---------------------------------------------------------------------------


class TestEnqueueDequeue:
    def test_enqueue_inbound_and_get(self, tmp_path):
        queue_path = str(tmp_path / "queue.db")
        q = get_inbound_queue(queue_path)
        env = MessageEnvelope(
            message_type=MessageType.INBOUND,
            caller_id="c1",
            payload={"operation": "spawn_worker"},
        )
        enqueue_inbound(q, env)

        raw = q.get(block=False)
        assert raw is not None
        data = json.loads(raw)
        assert data["caller_id"] == "c1"
        assert data["payload"]["operation"] == "spawn_worker"
        q.ack(raw)
        q.close()

    def test_enqueue_outbound_and_get(self, tmp_path):
        queue_path = str(tmp_path / "queue.db")
        q = get_outbound_queue(queue_path)
        env = MessageEnvelope(
            message_type=MessageType.OUTBOUND,
            caller_id="c2",
            payload={"type": "notify"},
        )
        enqueue_outbound(q, env)

        raw = q.get(block=False)
        assert raw is not None
        data = json.loads(raw)
        assert data["caller_id"] == "c2"
        q.ack(raw)
        q.close()


# ---------------------------------------------------------------------------
# Queue restart survival
# ---------------------------------------------------------------------------


class TestQueueRestartSurvival:
    def test_item_survives_queue_close_and_reopen(self, tmp_path):
        queue_path = str(tmp_path / "queue.db")
        env = MessageEnvelope(
            message_type=MessageType.INBOUND,
            caller_id="durable-caller",
            payload={"operation": "spawn_worker", "request_id": "req-99"},
        )

        # Put and close
        q = get_inbound_queue(queue_path)
        enqueue_inbound(q, env)
        q.close()

        # Reopen and get
        q2 = get_inbound_queue(queue_path)
        raw = q2.get(block=False)
        assert raw is not None
        data = json.loads(raw)
        assert data["caller_id"] == "durable-caller"
        assert data["payload"]["request_id"] == "req-99"
        q2.ack(raw)
        q2.close()


# ---------------------------------------------------------------------------
# Nack
# ---------------------------------------------------------------------------


class TestNack:
    def test_nack_requeues_item(self, tmp_path):
        queue_path = str(tmp_path / "queue.db")
        q = get_inbound_queue(queue_path)
        env = MessageEnvelope(
            message_type=MessageType.INBOUND,
            caller_id="nack-caller",
            payload={"operation": "spawn_worker"},
        )
        enqueue_inbound(q, env)

        # Get and nack
        raw = q.get(block=False)
        assert raw is not None
        q.nack(raw)

        # Should be available again
        raw2 = q.get(block=False)
        assert raw2 is not None
        data = json.loads(raw2)
        assert data["caller_id"] == "nack-caller"
        q.ack(raw2)
        q.close()


# ---------------------------------------------------------------------------
# InboundProcessor dispatch
# ---------------------------------------------------------------------------


class _StopLoop(Exception):
    """Sentinel raised to break infinite processor loops in tests."""


class TestInboundProcessorDispatch:
    """Tests for inbound_processor.process_inbound dispatch logic."""

    def _make_queue_mock(self, envelope: MessageEnvelope):
        """Return a mock queue that yields one item then raises Empty."""
        call_count = 0

        def side_effect(block=True):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return json.dumps(envelope.to_dict())
            raise Exception("empty")

        q = MagicMock()
        q.get.side_effect = side_effect
        q.ack = MagicMock()
        return q

    async def _run_one(self, queue_mock):
        """Run process_inbound until it sleeps (i.e., queue empty)."""
        from waggle import inbound_processor
        with patch("asyncio.sleep", new=AsyncMock(side_effect=_StopLoop)):
            try:
                await inbound_processor.process_inbound(queue_mock)
            except _StopLoop:
                pass

    @pytest.mark.asyncio
    async def test_dispatch_spawn_worker(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        from waggle.database import init_schema
        init_schema(db_path)

        env = MessageEnvelope(
            message_type=MessageType.INBOUND,
            caller_id="c1",
            payload={
                "operation": "spawn_worker",
                "request_id": "req-1",
                "model": "sonnet",
                "repo": "/repo",
                "session_name": None,
                "command": None,
            },
        )
        q = self._make_queue_mock(env)

        with patch("waggle.engine.spawn_worker", new=AsyncMock(return_value={"worker_id": "w-1"})) as mock_spawn, \
             patch("waggle.config.get_db_path", return_value=db_path), \
             patch("waggle.database.complete_request") as mock_complete:
            await self._run_one(q)

        mock_spawn.assert_called_once_with("c1", "sonnet", "/repo", None, None)
        mock_complete.assert_called_once_with(db_path, "req-1", json.dumps({"worker_id": "w-1"}))
        q.ack.assert_called_once()

    @pytest.mark.asyncio
    async def test_dispatch_send_input(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        from waggle.database import init_schema
        init_schema(db_path)

        env = MessageEnvelope(
            message_type=MessageType.INBOUND,
            caller_id="c1",
            payload={
                "operation": "send_input",
                "request_id": "req-2",
                "worker_id": "w-1",
                "text": "hello",
            },
        )
        q = self._make_queue_mock(env)

        with patch("waggle.engine.send_input", new=AsyncMock(return_value={"status": "ok"})) as mock_send, \
             patch("waggle.config.get_db_path", return_value=db_path), \
             patch("waggle.database.complete_request") as mock_complete:
            await self._run_one(q)

        mock_send.assert_called_once_with("c1", "w-1", "hello")
        mock_complete.assert_called_once_with(db_path, "req-2", json.dumps({"status": "ok"}))
        q.ack.assert_called_once()

    @pytest.mark.asyncio
    async def test_dispatch_terminate_worker(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        from waggle.database import init_schema
        init_schema(db_path)

        env = MessageEnvelope(
            message_type=MessageType.INBOUND,
            caller_id="c1",
            payload={
                "operation": "terminate_worker",
                "request_id": "req-3",
                "worker_id": "w-1",
            },
        )
        q = self._make_queue_mock(env)

        with patch("waggle.engine.terminate_worker", new=AsyncMock(return_value={"status": "done"})) as mock_term, \
             patch("waggle.config.get_db_path", return_value=db_path), \
             patch("waggle.database.complete_request") as mock_complete:
            await self._run_one(q)

        mock_term.assert_called_once_with("c1", "w-1")
        mock_complete.assert_called_once_with(db_path, "req-3", json.dumps({"status": "done"}))
        q.ack.assert_called_once()

    @pytest.mark.asyncio
    async def test_engine_error_calls_fail_request(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        from waggle.database import init_schema
        init_schema(db_path)

        env = MessageEnvelope(
            message_type=MessageType.INBOUND,
            caller_id="c1",
            payload={
                "operation": "spawn_worker",
                "request_id": "req-4",
                "model": "sonnet",
                "repo": "/repo",
                "session_name": None,
                "command": None,
            },
        )
        q = self._make_queue_mock(env)

        with patch("waggle.engine.spawn_worker", new=AsyncMock(return_value={"error": "tmux_failed"})), \
             patch("waggle.config.get_db_path", return_value=db_path), \
             patch("waggle.database.fail_request") as mock_fail, \
             patch("waggle.database.complete_request") as mock_complete:
            await self._run_one(q)

        mock_fail.assert_called_once_with(db_path, "req-4", json.dumps({"error": "tmux_failed"}))
        mock_complete.assert_not_called()
        q.ack.assert_called_once()


# ---------------------------------------------------------------------------
# OutboundProcessor
# ---------------------------------------------------------------------------


class TestOutboundProcessorStub:
    """Verify outbound processor dequeues and acks messages."""

    @pytest.mark.asyncio
    async def test_dequeues_and_acks(self):
        env = MessageEnvelope(
            message_type=MessageType.OUTBOUND,
            caller_id="c-out",
            payload={"type": "status_update"},
        )
        raw = json.dumps(env.to_dict())

        call_count = 0

        def get_side_effect(block=True):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return raw
            raise Exception("empty")

        q = MagicMock()
        q.get.side_effect = get_side_effect
        q.ack = MagicMock()

        from waggle import outbound_processor
        with patch("asyncio.sleep", new=AsyncMock(side_effect=_StopLoop)):
            try:
                await outbound_processor.process_outbound(q)
            except _StopLoop:
                pass

        q.ack.assert_called_once_with(raw)
