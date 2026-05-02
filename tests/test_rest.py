"""Tests for waggle REST API route handlers (rest.py)."""

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.routing import Mount
from starlette.testclient import TestClient

from waggle import engine, rest
from waggle.database import init_schema, connection


# ---------------------------------------------------------------------------
# Test app setup
# ---------------------------------------------------------------------------


class MockAuthMiddleware(BaseHTTPMiddleware):
    """Inject a fixed caller_id without SSH verification."""

    def __init__(self, app, caller_id="test-caller"):
        super().__init__(app)
        self._caller_id = caller_id

    async def dispatch(self, request: Request, call_next):
        request.state.caller_id = self._caller_id
        return await call_next(request)


def _make_app(caller_id="test-caller"):
    app = Starlette(routes=[Mount("/api/v1", app=rest.rest_router)])
    app.add_middleware(MockAuthMiddleware, caller_id=caller_id)
    return app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    """Temp SQLite DB wired into engine and rest module."""
    path = str(tmp_path / "test.db")
    init_schema(path)

    mock_config = {
        "database_path": path,
        "max_workers": 3,
        "repos_path": str(tmp_path / "repos"),
        "authorized_keys_path": str(tmp_path / "authorized_keys.json"),
    }

    monkeypatch.setattr("waggle.config.get_config", lambda: mock_config)
    monkeypatch.setattr("waggle.engine._db_path", lambda: path)
    monkeypatch.setattr("waggle.rest.config.get_db_path", lambda: path)
    return path


@pytest.fixture
def mock_queue():
    """Provide a mock queue and patch enqueue_inbound."""
    q = MagicMock()
    with patch("waggle.rest.enqueue_inbound") as mock_enqueue:
        mock_enqueue.return_value = None
        rest.set_inbound_queue(q)
        yield mock_enqueue
    rest.set_inbound_queue(None)


@pytest.fixture
def client(db_path, mock_queue):
    return TestClient(_make_app(), raise_server_exceptions=True)


@pytest.fixture
def registered(db_path):
    """Register test-caller in the DB."""
    asyncio.run(engine.register_caller("test-caller", "local"))
    return "test-caller"


def _insert_worker(db_path, caller_id="test-caller", status="working"):
    worker_id = str(uuid.uuid4())
    session_name = f"waggle-{worker_id[:8]}"
    session_id = f"${uuid.uuid4().hex[:4]}"
    with connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO workers
                (worker_id, caller_id, session_name, session_id, model, repo, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (worker_id, caller_id, session_name, session_id, "sonnet", "/repo", status),
        )
    return worker_id, session_id, session_name


def _insert_pending_relay(db_path, worker_id, relay_type="permission"):
    relay_id = str(uuid.uuid4())
    with connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO pending_relays
                (relay_id, worker_id, relay_type, details, status)
            VALUES (?, ?, ?, '{}', 'pending')
            """,
            (relay_id, worker_id, relay_type),
        )
    return relay_id


# ---------------------------------------------------------------------------
# POST /api/v1/register
# ---------------------------------------------------------------------------


class TestRegister:
    def test_register_returns_200(self, client):
        resp = client.post("/api/v1/register", json={"caller_type": "local"})
        assert resp.status_code == 200

    def test_register_returns_caller_id(self, client):
        resp = client.post("/api/v1/register", json={"caller_type": "local"})
        assert resp.json()["caller_id"] == "test-caller"

    def test_register_with_cma_type(self, client):
        resp = client.post(
            "/api/v1/register",
            json={"caller_type": "cma", "cma_session_id": "sess-001"},
        )
        assert resp.status_code == 200
        assert resp.json()["caller_id"] == "test-caller"


# ---------------------------------------------------------------------------
# GET /api/v1/workers
# ---------------------------------------------------------------------------


class TestListWorkers:
    def test_empty_list(self, client, registered):
        resp = client.get("/api/v1/workers")
        assert resp.status_code == 200
        assert resp.json()["workers"] == []

    def test_returns_registered_workers(self, client, db_path, registered):
        w1, _, _ = _insert_worker(db_path)
        w2, _, _ = _insert_worker(db_path)
        resp = client.get("/api/v1/workers")
        assert resp.status_code == 200
        ids = {w["worker_id"] for w in resp.json()["workers"]}
        assert ids == {w1, w2}

    def test_caller_isolation(self, db_path, mock_queue, registered):
        # Insert a worker for another caller
        asyncio.run(engine.register_caller("other-caller", "local"))
        _insert_worker(db_path, caller_id="other-caller")
        my_worker, _, _ = _insert_worker(db_path, caller_id="test-caller")

        client_a = TestClient(_make_app("test-caller"), raise_server_exceptions=True)
        resp = client_a.get("/api/v1/workers")
        ids = {w["worker_id"] for w in resp.json()["workers"]}
        assert ids == {my_worker}


# ---------------------------------------------------------------------------
# POST /api/v1/workers (spawn)
# ---------------------------------------------------------------------------


class TestSpawnWorker:
    def test_spawn_returns_202_and_request_id(self, client, registered):
        resp = client.post(
            "/api/v1/workers",
            json={"model": "sonnet", "repo": "/local/repo"},
        )
        assert resp.status_code == 202
        assert "request_id" in resp.json()

    def test_spawn_enqueues_message(self, client, registered, mock_queue):
        client.post("/api/v1/workers", json={"model": "sonnet", "repo": "/local/repo"})
        mock_queue.assert_called_once()

    def test_spawn_creates_request_record(self, client, db_path, registered):
        resp = client.post("/api/v1/workers", json={"model": "haiku"})
        request_id = resp.json()["request_id"]
        with connection(db_path) as conn:
            row = conn.execute(
                "SELECT * FROM requests WHERE request_id = ?", (request_id,)
            ).fetchone()
        assert row is not None
        assert row["operation"] == "spawn_worker"

    def test_concurrency_limit_returns_409(self, client, db_path, registered):
        # Fill up to max_workers (3)
        for _ in range(3):
            _insert_worker(db_path)
        resp = client.post("/api/v1/workers", json={"model": "sonnet"})
        assert resp.status_code == 409
        assert resp.json()["error"] == "concurrency_limit_reached"


# ---------------------------------------------------------------------------
# GET /api/v1/workers/{id}/status
# ---------------------------------------------------------------------------


class TestCheckStatus:
    def test_existing_worker_returns_200(self, client, db_path, registered):
        worker_id, _, _ = _insert_worker(db_path)
        resp = client.get(f"/api/v1/workers/{worker_id}/status")
        assert resp.status_code == 200
        assert resp.json()["worker_id"] == worker_id

    def test_nonexistent_worker_returns_404(self, client, registered):
        resp = client.get(f"/api/v1/workers/{uuid.uuid4()}/status")
        assert resp.status_code == 404
        assert resp.json()["error"] == "worker_not_found"

    def test_wrong_caller_returns_404(self, db_path, mock_queue, registered):
        asyncio.run(engine.register_caller("other", "local"))
        worker_id, _, _ = _insert_worker(db_path, caller_id="other")
        # Access with test-caller
        c = TestClient(_make_app("test-caller"), raise_server_exceptions=True)
        resp = c.get(f"/api/v1/workers/{worker_id}/status")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/v1/workers/{id}/output
# ---------------------------------------------------------------------------


class TestGetOutput:
    def test_existing_worker_returns_200(self, client, db_path, registered):
        worker_id, session_id, _ = _insert_worker(db_path)
        with patch("waggle.engine.tmux.capture_pane", new_callable=AsyncMock) as mock_cap:
            mock_cap.return_value = {"status": "success", "content": "line1\nline2"}
            resp = client.get(f"/api/v1/workers/{worker_id}/output")
        assert resp.status_code == 200
        assert resp.json()["lines"] == "line1\nline2"

    def test_nonexistent_worker_returns_404(self, client, registered):
        resp = client.get(f"/api/v1/workers/{uuid.uuid4()}/output")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/v1/workers/{id}/approve
# ---------------------------------------------------------------------------


class TestApprovePermission:
    def test_approve_with_pending_relay_returns_200(self, client, db_path, registered):
        worker_id, _, _ = _insert_worker(db_path)
        _insert_pending_relay(db_path, worker_id, relay_type="permission")
        resp = client.post(
            f"/api/v1/workers/{worker_id}/approve",
            json={"decision": "allow"},
        )
        assert resp.status_code == 200

    def test_approve_nonexistent_worker_returns_404(self, client, registered):
        resp = client.post(
            f"/api/v1/workers/{uuid.uuid4()}/approve",
            json={"decision": "allow"},
        )
        assert resp.status_code == 404

    def test_approve_no_pending_relay_returns_404(self, client, db_path, registered):
        worker_id, _, _ = _insert_worker(db_path)
        resp = client.post(
            f"/api/v1/workers/{worker_id}/approve",
            json={"decision": "allow"},
        )
        assert resp.status_code == 404
        assert resp.json()["error"] == "no_pending_permission"


# ---------------------------------------------------------------------------
# POST /api/v1/workers/{id}/answer
# ---------------------------------------------------------------------------


class TestAnswerQuestion:
    def test_answer_with_pending_relay_returns_200(self, client, db_path, registered):
        worker_id, _, _ = _insert_worker(db_path)
        _insert_pending_relay(db_path, worker_id, relay_type="ask")
        resp = client.post(
            f"/api/v1/workers/{worker_id}/answer",
            json={"answer": "yes"},
        )
        assert resp.status_code == 200

    def test_answer_nonexistent_worker_returns_404(self, client, registered):
        resp = client.post(
            f"/api/v1/workers/{uuid.uuid4()}/answer",
            json={"answer": "yes"},
        )
        assert resp.status_code == 404

    def test_answer_no_pending_question_returns_404(self, client, db_path, registered):
        worker_id, _, _ = _insert_worker(db_path)
        resp = client.post(
            f"/api/v1/workers/{worker_id}/answer",
            json={"answer": "yes"},
        )
        assert resp.status_code == 404
        assert resp.json()["error"] == "no_pending_question"


# ---------------------------------------------------------------------------
# DELETE /api/v1/workers/{id}
# ---------------------------------------------------------------------------


class TestTerminateWorker:
    def test_terminate_existing_worker_returns_202(self, client, db_path, registered):
        worker_id, _, _ = _insert_worker(db_path)
        resp = client.delete(f"/api/v1/workers/{worker_id}")
        assert resp.status_code == 202
        assert "request_id" in resp.json()

    def test_terminate_enqueues_message(self, client, db_path, registered, mock_queue):
        worker_id, _, _ = _insert_worker(db_path)
        mock_queue.reset_mock()
        client.delete(f"/api/v1/workers/{worker_id}")
        mock_queue.assert_called_once()

    def test_terminate_nonexistent_worker_returns_404(self, client, registered):
        resp = client.delete(f"/api/v1/workers/{uuid.uuid4()}")
        assert resp.status_code == 404
        assert resp.json()["error"] == "worker_not_found"

    def test_terminate_wrong_caller_returns_404(self, db_path, mock_queue, registered):
        asyncio.run(engine.register_caller("other", "local"))
        worker_id, _, _ = _insert_worker(db_path, caller_id="other")
        c = TestClient(_make_app("test-caller"), raise_server_exceptions=True)
        resp = c.delete(f"/api/v1/workers/{worker_id}")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/v1/requests/{id}
# ---------------------------------------------------------------------------


class TestCheckRequest:
    def test_existing_request_returns_200(self, client, db_path, registered):
        # Create a request by spawning
        resp = client.post("/api/v1/workers", json={"model": "sonnet"})
        request_id = resp.json()["request_id"]
        resp2 = client.get(f"/api/v1/requests/{request_id}")
        assert resp2.status_code == 200
        assert resp2.json()["request_id"] == request_id

    def test_nonexistent_request_returns_404(self, client, registered):
        resp = client.get(f"/api/v1/requests/{uuid.uuid4()}")
        assert resp.status_code == 404
        assert resp.json()["error"] == "request_not_found"


# ---------------------------------------------------------------------------
# Error response format
# ---------------------------------------------------------------------------


class TestErrorFormat:
    def test_error_response_has_error_and_message_keys(self, client, registered):
        resp = client.get(f"/api/v1/workers/{uuid.uuid4()}/status")
        body = resp.json()
        assert "error" in body
        assert "message" in body
        assert isinstance(body["error"], str)
        assert isinstance(body["message"], str)


# ---------------------------------------------------------------------------
# Caller scoping / isolation
# ---------------------------------------------------------------------------


class TestCallerScoping:
    def test_caller_a_cannot_see_caller_b_workers(self, db_path, mock_queue):
        asyncio.run(engine.register_caller("caller-a", "local"))
        asyncio.run(engine.register_caller("caller-b", "local"))
        _insert_worker(db_path, caller_id="caller-b")

        client_a = TestClient(_make_app("caller-a"), raise_server_exceptions=True)
        resp = client_a.get("/api/v1/workers")
        assert resp.json()["workers"] == []

    def test_caller_a_cannot_terminate_caller_b_worker(self, db_path, mock_queue):
        asyncio.run(engine.register_caller("caller-a", "local"))
        asyncio.run(engine.register_caller("caller-b", "local"))
        worker_id, _, _ = _insert_worker(db_path, caller_id="caller-b")

        client_a = TestClient(_make_app("caller-a"), raise_server_exceptions=True)
        resp = client_a.delete(f"/api/v1/workers/{worker_id}")
        assert resp.status_code == 404
