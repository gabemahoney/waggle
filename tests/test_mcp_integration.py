"""Integration tests for the waggle v2 MCP server engine.

Tests the server tool functions against a real temp SQLite DB with all tmux
operations mocked. ctx=None causes _get_caller_id to return "local", which is
sufficient for single-caller tests; multi-caller tests call engine directly.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from waggle import engine, server
from waggle.database import init_schema

# FastMCP 2.x wraps decorated functions into FunctionTool objects; .fn is the original callable.
check_status = server.check_status.fn
get_output = server.get_output.fn
list_workers = server.list_workers.fn
register_caller = server.register_caller.fn
send_input = server.send_input.fn
spawn_worker = server.spawn_worker.fn
terminate_worker = server.terminate_worker.fn


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    """Temp SQLite DB wired into the engine with max_workers=3."""
    path = str(tmp_path / "test.db")
    init_schema(path)
    monkeypatch.setattr("waggle.engine._db_path", lambda: path)
    monkeypatch.setattr(
        "waggle.engine.config.get_config",
        lambda: {
            "database_path": path,
            "max_workers": 3,
            "repos_path": str(tmp_path / "repos"),
            "mcp_worker_port": 8423,
        },
    )
    return path


@pytest.fixture
def mock_tmux():
    """Mock all tmux operations so no real tmux session is needed."""
    with (
        patch(
            "waggle.engine.tmux.clone_or_update_repo_async",
            new_callable=AsyncMock,
        ) as mock_clone,
        patch(
            "waggle.engine.tmux.create_session",
            new_callable=AsyncMock,
        ) as mock_create,
        patch(
            "waggle.engine.tmux.launch_agent_in_pane",
            new_callable=AsyncMock,
        ) as mock_launch,
        patch(
            "waggle.engine.tmux.capture_pane",
            new_callable=AsyncMock,
        ) as mock_capture,
        patch(
            "waggle.engine.tmux.kill_session",
            new_callable=AsyncMock,
        ) as mock_kill,
    ):
        mock_clone.return_value = "/local/repo"
        mock_create.return_value = {
            "status": "success",
            "session_id": "$1",
            "session_name": "test-session",
            "session_created": "1234567890",
            "worker_id": "mock-id",
        }
        mock_launch.return_value = {"status": "success"}
        mock_capture.return_value = {"status": "success", "content": "test output"}
        mock_kill.return_value = {"status": "success"}
        yield {
            "clone": mock_clone,
            "create": mock_create,
            "launch": mock_launch,
            "capture": mock_capture,
            "kill": mock_kill,
        }


# ---------------------------------------------------------------------------
# Test 1: Full lifecycle
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_lifecycle(db_path, mock_tmux):
    """register → spawn → list → check_status → get_output → terminate → empty list."""
    # register_caller
    result = await register_caller(caller_type="local", ctx=None)
    assert result == {"caller_id": "local"}

    # spawn_worker
    result = await spawn_worker(model="sonnet", repo="/some/repo", ctx=None)
    assert "worker_id" in result
    assert "session_name" in result
    worker_id = result["worker_id"]

    # list_workers — one worker visible
    result = await list_workers(ctx=None)
    assert "workers" in result
    workers = result["workers"]
    assert len(workers) == 1
    assert workers[0]["worker_id"] == worker_id

    # check_status
    result = await check_status(worker_id=worker_id, ctx=None)
    assert result["worker_id"] == worker_id
    assert result["status"] == "working"
    assert "output_lines" in result
    assert "updated_at" in result
    assert result["pending_relay"] is None

    # get_output
    result = await get_output(worker_id=worker_id, ctx=None)
    assert result["worker_id"] == worker_id
    assert result["lines"] == "test output"

    # terminate_worker
    result = await terminate_worker(worker_id=worker_id, ctx=None)
    assert result == {"worker_id": worker_id, "terminated": True}

    # list_workers — empty after termination
    result = await list_workers(ctx=None)
    assert result["workers"] == []


# ---------------------------------------------------------------------------
# Test 2: Caller scoping
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_caller_scoping(db_path, mock_tmux):
    """Each caller only sees and can manage their own workers."""
    await engine.register_caller("caller-a", "local")
    await engine.register_caller("caller-b", "local")

    r_a = await engine.spawn_worker("caller-a", "sonnet", "/repo-a")
    assert "worker_id" in r_a
    worker_a = r_a["worker_id"]

    r_b = await engine.spawn_worker("caller-b", "sonnet", "/repo-b")
    assert "worker_id" in r_b
    worker_b = r_b["worker_id"]

    # Each caller sees only their own worker
    workers_a = await engine.list_workers("caller-a")
    assert len(workers_a) == 1
    assert workers_a[0]["worker_id"] == worker_a

    workers_b = await engine.list_workers("caller-b")
    assert len(workers_b) == 1
    assert workers_b[0]["worker_id"] == worker_b

    # Cross-caller check_status denied
    result = await engine.check_status("caller-a", worker_b)
    assert result == {"error": "worker_not_found"}

    # Cross-caller terminate denied
    result = await engine.terminate_worker("caller-a", worker_b)
    assert result == {"error": "worker_not_found"}


# ---------------------------------------------------------------------------
# Test 3: Concurrency limit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_concurrency_limit(tmp_path, monkeypatch, mock_tmux):
    """Spawning beyond max_workers returns concurrency_limit_reached."""
    path = str(tmp_path / "limit_test.db")
    init_schema(path)
    monkeypatch.setattr("waggle.engine._db_path", lambda: path)
    monkeypatch.setattr(
        "waggle.engine.config.get_config",
        lambda: {
            "database_path": path,
            "max_workers": 2,
            "repos_path": str(tmp_path / "repos"),
            "mcp_worker_port": 8423,
        },
    )

    await engine.register_caller("local", "local")

    r1 = await engine.spawn_worker("local", "sonnet", "/repo")
    assert "worker_id" in r1

    r2 = await engine.spawn_worker("local", "sonnet", "/repo")
    assert "worker_id" in r2

    # Third spawn exceeds the limit
    r3 = await engine.spawn_worker("local", "sonnet", "/repo")
    assert r3 == {"error": "concurrency_limit_reached"}


# ---------------------------------------------------------------------------
# Test 4: Response shapes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_response_shapes(db_path, mock_tmux):
    """Each tool returns the SRD-specified fields with correct types."""
    # register_caller → {"caller_id": str}
    result = await register_caller(ctx=None)
    assert set(result.keys()) == {"caller_id"}
    assert isinstance(result["caller_id"], str)

    # spawn_worker → {"worker_id": str, "session_name": str}
    result = await spawn_worker(model="haiku", repo="/some/repo", ctx=None)
    assert set(result.keys()) == {"worker_id", "session_name"}
    assert isinstance(result["worker_id"], str)
    assert isinstance(result["session_name"], str)
    worker_id = result["worker_id"]

    # list_workers → {"workers": list}
    result = await list_workers(ctx=None)
    assert "workers" in result
    assert isinstance(result["workers"], list)

    # check_status → {"worker_id", "status", "output_lines", "updated_at", "pending_relay"}
    result = await check_status(worker_id=worker_id, ctx=None)
    assert "worker_id" in result
    assert "status" in result
    assert "output_lines" in result
    assert "updated_at" in result
    assert "pending_relay" in result

    # get_output → {"worker_id": str, "lines": str}
    result = await get_output(worker_id=worker_id, ctx=None)
    assert set(result.keys()) == {"worker_id", "lines"}
    assert isinstance(result["worker_id"], str)
    assert isinstance(result["lines"], str)

    # terminate_worker → {"worker_id": str, "terminated": True}
    result = await terminate_worker(worker_id=worker_id, ctx=None)
    assert result["worker_id"] == worker_id
    assert result["terminated"] is True


# ---------------------------------------------------------------------------
# Test 5: send_input (Claude Channels)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_input_integration(db_path, mock_tmux):
    """send_input delivers to a connected worker; errors on disconnected."""
    await register_caller(caller_type="local", ctx=None)
    result = await spawn_worker(model="sonnet", repo="/some/repo", ctx=None)
    worker_id = result["worker_id"]

    # Worker not yet in registry → worker_not_connected
    with patch("waggle.worker_mcp.registry") as mock_registry:
        mock_registry.get.return_value = None
        result = await send_input(worker_id=worker_id, text="hello", ctx=None)
    assert result == {"error": "worker_not_connected"}

    # Worker connects (added to registry with a mock session)
    mock_session = MagicMock()
    mock_session._write_stream.send = AsyncMock()

    with patch("waggle.worker_mcp.registry") as mock_registry:
        mock_registry.get.return_value = mock_session
        result = await send_input(worker_id=worker_id, text="hello", ctx=None)

    assert result == {"worker_id": worker_id, "delivered": True}
    mock_session._write_stream.send.assert_awaited_once()
