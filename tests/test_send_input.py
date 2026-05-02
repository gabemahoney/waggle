"""Unit tests for send_input — tmux send-keys delivery."""

import uuid
import pytest
from unittest.mock import AsyncMock, patch

from waggle import engine
from waggle.database import init_schema, connection


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    """Temp DB with schema; engine patched to use it."""
    path = str(tmp_path / "test.db")
    init_schema(path)
    monkeypatch.setattr("waggle.engine._db_path", lambda: path)
    monkeypatch.setattr(
        "waggle.engine.config.get_config",
        lambda: {
            "database_path": path,
            "max_workers": 3,
            "repos_path": str(tmp_path / "repos"),
        },
    )
    return path


def _insert_worker(db_path, caller_id="test-caller", status="working"):
    worker_id = str(uuid.uuid4())
    session_name = f"waggle-{worker_id[:8]}"
    session_id = f"${uuid.uuid4().hex[:4]}"
    with connection(db_path) as conn:
        conn.execute(
            """INSERT INTO workers
               (worker_id, caller_id, session_name, session_id, model, repo, status)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (worker_id, caller_id, session_name, session_id, "sonnet", "/repo", status),
        )
    return worker_id, session_id


# ---------------------------------------------------------------------------
# send_input tests
# ---------------------------------------------------------------------------


class TestSendInput:
    @pytest.mark.asyncio
    async def test_send_input_success(self, db_path):
        """Worker in DB → tmux.send_keys called with correct session_id and text → delivered: True."""
        worker_id, session_id = _insert_worker(db_path, caller_id="test-caller")

        with patch("waggle.engine.tmux.send_keys", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = {"status": "success"}
            result = await engine.send_input("test-caller", worker_id, "hello")

        assert result == {"worker_id": worker_id, "delivered": True}
        mock_send.assert_awaited_once_with(session_id, "hello")

    @pytest.mark.asyncio
    async def test_send_input_worker_not_found(self, db_path):
        """worker_id not in DB → error: worker_not_found."""
        fake_id = str(uuid.uuid4())
        result = await engine.send_input("test-caller", fake_id, "hello")
        assert result == {"error": "worker_not_found"}

    @pytest.mark.asyncio
    async def test_send_input_wrong_caller(self, db_path):
        """Worker exists but different caller → error: worker_not_found."""
        worker_id, _ = _insert_worker(db_path, caller_id="test-caller")
        result = await engine.send_input("wrong-caller", worker_id, "hello")
        assert result == {"error": "worker_not_found"}

    @pytest.mark.asyncio
    async def test_send_input_tmux_error(self, db_path):
        """Worker exists but tmux.send_keys returns error → returns error message."""
        worker_id, session_id = _insert_worker(db_path, caller_id="test-caller")

        with patch("waggle.engine.tmux.send_keys", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = {"status": "error", "message": "no such session"}
            result = await engine.send_input("test-caller", worker_id, "hello")

        assert result == {"error": "no such session"}
