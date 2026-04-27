"""Unit tests for waggle.worker_mcp module — WorkerRegistry and worker registration."""

import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from waggle.database import init_schema, connection
from waggle.worker_mcp import WorkerRegistry, register_worker


# ---------------------------------------------------------------------------
# WorkerRegistry
# ---------------------------------------------------------------------------


class TestWorkerRegistry:
    def test_register_and_get(self):
        reg = WorkerRegistry()
        mock_session = MagicMock()
        reg.register("worker-1", mock_session)
        assert reg.get("worker-1") is mock_session

    def test_get_unregistered_returns_none(self):
        reg = WorkerRegistry()
        assert reg.get("nonexistent") is None

    def test_unregister(self):
        reg = WorkerRegistry()
        mock_session = MagicMock()
        reg.register("worker-1", mock_session)
        reg.unregister("worker-1")
        assert reg.get("worker-1") is None

    def test_unregister_nonexistent_no_error(self):
        reg = WorkerRegistry()
        reg.unregister("nonexistent")  # must not raise

    def test_register_overwrites(self):
        reg = WorkerRegistry()
        session_1 = MagicMock()
        session_2 = MagicMock()
        reg.register("worker-1", session_1)
        reg.register("worker-1", session_2)
        assert reg.get("worker-1") is session_2


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    """Temp DB with schema; config and _db_path patched to use it."""
    path = str(tmp_path / "test.db")
    init_schema(path)
    monkeypatch.setattr(
        "waggle.config.get_config",
        lambda: {
            "database_path": path,
            "max_workers": 3,
            "repos_path": str(tmp_path / "repos"),
            "mcp_worker_port": 8423,
        },
    )
    monkeypatch.setattr("waggle.worker_mcp._db_path", lambda: path)
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
    return worker_id


# FastMCP 2.x wraps decorated functions into FunctionTool objects; .fn is the original callable.
register_worker_fn = register_worker.fn


# ---------------------------------------------------------------------------
# register_worker tool
# ---------------------------------------------------------------------------


class TestRegisterWorkerTool:
    @pytest.mark.asyncio
    async def test_register_worker_success(self, db_path):
        """Valid worker_id in query params + exists in DB → registered: True."""
        worker_id = _insert_worker(db_path)

        mock_request = MagicMock()
        mock_request.query_params.get.return_value = worker_id

        mock_ctx = MagicMock()
        mock_ctx.session_id = "test-session-id"
        mock_ctx.session = MagicMock()

        with patch("waggle.worker_mcp.get_http_request", return_value=mock_request):
            result = await register_worker_fn(ctx=mock_ctx)

        assert result["worker_id"] == worker_id
        assert result["registered"] is True

    @pytest.mark.asyncio
    async def test_register_worker_missing_worker_id(self, db_path):
        """No worker_id in query params → error: worker_id_required."""
        mock_request = MagicMock()
        mock_request.query_params.get.return_value = None

        mock_ctx = MagicMock()

        with patch("waggle.worker_mcp.get_http_request", return_value=mock_request):
            result = await register_worker_fn(ctx=mock_ctx)

        assert result == {"error": "worker_id_required"}

    @pytest.mark.asyncio
    async def test_register_worker_not_found(self, db_path):
        """worker_id not in DB → error: worker_not_found."""
        mock_request = MagicMock()
        mock_request.query_params.get.return_value = str(uuid.uuid4())

        mock_ctx = MagicMock()

        with patch("waggle.worker_mcp.get_http_request", return_value=mock_request):
            result = await register_worker_fn(ctx=mock_ctx)

        assert result == {"error": "worker_not_found"}

    @pytest.mark.asyncio
    async def test_register_worker_no_context(self, db_path):
        """ctx=None → error: no_context."""
        result = await register_worker_fn(ctx=None)
        assert result == {"error": "no_context"}
