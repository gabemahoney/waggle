"""Tests for the claude_spawn stdio MCP server (t1.fg8.vv).

Verifies tool registration count, SR-7.1 error wrapping, and that no
TCP/UDS socket is bound by the module.  No conftest.py.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

import claude_spawn.mcp_stdio as ms
from tests.helpers import fake_claude_status, fake_workers_response


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------


_EXPECTED_TOOLS = {
    "spawn_worker",
    "list_spawned_workers",
    "send_input",
    "get_output",
    "terminate_worker",
    "answer_question",
}


class TestToolRegistration:
    def test_exactly_six_tools_registered(self):
        tools = ms.mcp._tool_manager._tools
        assert len(tools) == 6, f"expected 6 tools, got {len(tools)}: {list(tools)}"

    def test_all_expected_tools_registered(self):
        tools = ms.mcp._tool_manager._tools
        missing = _EXPECTED_TOOLS - tools.keys()
        assert not missing, f"tools missing from server: {missing}"

    def test_no_deprecated_tools(self):
        """Ensure old daemon tools are not registered."""
        tools = ms.mcp._tool_manager._tools
        forbidden = {"register_caller", "list_workers", "check_status", "approve_permission"}
        overlap = forbidden & tools.keys()
        assert not overlap, f"old tools found in new server: {overlap}"

    def test_server_name_is_claude_spawn_stdio(self):
        assert ms.mcp.name == "claude-spawn-stdio"


# ---------------------------------------------------------------------------
# SR-7.1 error wrapping — spawn_worker
# ---------------------------------------------------------------------------


class TestSpawnWorkerErrorWrapping:
    @pytest.mark.asyncio
    async def test_exception_becomes_operation_failed(self):
        with patch("claude_spawn.spawn.spawn_worker_impl", side_effect=RuntimeError("boom")):
            result = await ms.spawn_worker.fn(cwd="/tmp")
        assert result["ok"] is False
        assert result["err_name"] == "ErrUnexpected"
        assert "boom" in result["err_description"]

    @pytest.mark.asyncio
    async def test_tmux_failure_propagates_as_operation_failed(self):
        with patch("claude_spawn.spawn._tmux", return_value=("", "session exists", 1)):
            result = await ms.spawn_worker.fn(cwd="/tmp")
        assert result.get("ok") is False

    @pytest.mark.asyncio
    async def test_success_returns_id_pair(self):
        import json
        from tests.helpers import fake_worker_record, fake_workers_response
        _IID = "mcp-test-iid-0000-4000-8000-000000000001"
        rec = fake_worker_record(_IID, "working", cwd="/tmp")
        precheck = (json.dumps(fake_workers_response([])), "", 0)
        readiness = (json.dumps(fake_workers_response([rec])), "", 0)
        with patch("claude_spawn.spawn._tmux", return_value=("", "", 0)):
            with fake_claude_status([precheck, readiness]):
                result = await ms.spawn_worker.fn(
                    cwd="/tmp", tmux_session_name="my-sess", instance_id=_IID
                )
        assert "instance_id" in result
        assert result["tmux_session_name"] == "my-sess"


# ---------------------------------------------------------------------------
# SR-7.1 error wrapping — list_spawned_workers
# ---------------------------------------------------------------------------


class TestListSpawnedWorkersErrorWrapping:
    @pytest.mark.asyncio
    async def test_exception_becomes_operation_failed(self):
        with patch("claude_spawn.spawn.list_spawned_workers_impl", side_effect=RuntimeError("oops")):
            result = await ms.list_spawned_workers.fn()
        assert result["ok"] is False
        assert result["err_name"] == "ErrUnexpected"

    @pytest.mark.asyncio
    async def test_claude_status_error_propagates(self):
        from tests.sample_payloads import STDERR_ERR_STORE_UNAVAILABLE
        with fake_claude_status([("", STDERR_ERR_STORE_UNAVAILABLE, 1)]):
            result = await ms.list_spawned_workers.fn()
        assert result.get("ok") is False

    @pytest.mark.asyncio
    async def test_happy_path_returns_workers_list(self):
        from tests.helpers import fake_worker_record
        r = fake_worker_record("inst-xyz", "working")
        payload = json.dumps(fake_workers_response([r]))
        with fake_claude_status([(payload, "", 0)]):
            result = await ms.list_spawned_workers.fn()
        assert "workers" in result
        assert result["workers"][0]["instance_id"] == "inst-xyz"


# ---------------------------------------------------------------------------
# No TCP/UDS binding at import time
# ---------------------------------------------------------------------------


def test_import_does_not_bind_socket():
    """Confirm the module has no module-level socket binding."""
    import socket
    with patch.object(socket.socket, "bind", side_effect=AssertionError("bound a socket at import")):
        import importlib
        import claude_spawn.mcp_stdio
        importlib.reload(claude_spawn.mcp_stdio)
    # If we reach here, no socket was bound at module load.
