"""Tests for waggle/cma_client.py."""

import httpx
import pytest

from waggle.cma_client import CMAClient, CMARetryableError, CMATerminalError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_handler(status_code: int, json_body=None):
    """Return an httpx MockTransport handler that responds with the given status."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json=json_body or {})

    return handler


def make_transport_error_handler():
    """Return a handler that raises a TransportError."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("simulated transport error")

    return handler


_TEST_HEADERS = {
    "x-api-key": "test-key",
    "anthropic-version": "2023-06-01",
    "anthropic-beta": "managed-agents-2026-04-01",
}


def make_client(handler) -> CMAClient:
    client = CMAClient(api_key="test-key", base_url="http://test")
    client._client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="http://test",
        headers=_TEST_HEADERS,
    )
    return client


# ---------------------------------------------------------------------------
# URL / Headers / Body tests
# ---------------------------------------------------------------------------


class TestSendWorkerEventRequest:
    @pytest.mark.asyncio
    async def test_correct_url(self):
        captured: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured.append(request)
            return httpx.Response(200, json={})

        client = make_client(handler)
        await client.send_worker_event(
            cma_session_id="sess-123",
            worker_id="w-1",
            session_name="mysession",
            status="running",
            output="some output",
        )
        assert len(captured) == 1
        assert captured[0].url.path == "/v1/sessions/sess-123/events"
        await client.aclose()

    @pytest.mark.asyncio
    async def test_correct_headers(self):
        captured: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured.append(request)
            return httpx.Response(200, json={})

        client = make_client(handler)
        await client.send_worker_event(
            cma_session_id="sess-abc",
            worker_id="w-2",
            session_name="s",
            status="done",
            output="",
        )
        req = captured[0]
        assert req.headers["x-api-key"] == "test-key"
        assert req.headers["anthropic-version"] == "2023-06-01"
        assert req.headers["anthropic-beta"] == "managed-agents-2026-04-01"
        await client.aclose()

    @pytest.mark.asyncio
    async def test_correct_body_format(self):
        captured: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured.append(request)
            return httpx.Response(200, json={})

        client = make_client(handler)
        await client.send_worker_event(
            cma_session_id="sess-1",
            worker_id="w-3",
            session_name="mysession",
            status="idle",
            output="hello",
        )
        import json

        body = json.loads(captured[0].content)
        assert "events" in body
        assert len(body["events"]) == 1
        event = body["events"][0]
        assert event["type"] == "user.message"
        assert isinstance(event["content"], list)
        assert event["content"][0]["type"] == "text"
        assert isinstance(event["content"][0]["text"], str)
        await client.aclose()

    @pytest.mark.asyncio
    async def test_body_text_contains_worker_and_status(self):
        captured: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured.append(request)
            return httpx.Response(200, json={})

        client = make_client(handler)
        await client.send_worker_event(
            cma_session_id="sess-1",
            worker_id="worker-42",
            session_name="test-session",
            status="finished",
            output="my output",
        )
        import json

        body = json.loads(captured[0].content)
        text = body["events"][0]["content"][0]["text"]
        assert "worker-42" in text
        assert "test-session" in text
        assert "finished" in text
        assert "my output" in text
        await client.aclose()

    @pytest.mark.asyncio
    async def test_with_pending_relay_includes_relay_details(self):
        captured: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured.append(request)
            return httpx.Response(200, json={})

        client = make_client(handler)
        await client.send_worker_event(
            cma_session_id="sess-1",
            worker_id="w-1",
            session_name="s",
            status="waiting",
            output="output",
            pending_relay={"relay_type": "bash", "details": "rm -rf /"},
        )
        import json

        body = json.loads(captured[0].content)
        text = body["events"][0]["content"][0]["text"]
        assert "bash" in text
        assert "rm -rf /" in text
        assert "Permission request" in text
        await client.aclose()

    @pytest.mark.asyncio
    async def test_without_pending_relay_no_relay_section(self):
        captured: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured.append(request)
            return httpx.Response(200, json={})

        client = make_client(handler)
        await client.send_worker_event(
            cma_session_id="sess-1",
            worker_id="w-1",
            session_name="s",
            status="running",
            output="output",
            pending_relay=None,
        )
        import json

        body = json.loads(captured[0].content)
        text = body["events"][0]["content"][0]["text"]
        assert "Permission request" not in text
        await client.aclose()


# ---------------------------------------------------------------------------
# Response status code tests
# ---------------------------------------------------------------------------


class TestSendWorkerEventResponses:
    @pytest.mark.asyncio
    async def test_200_success(self):
        client = make_client(make_handler(200))
        await client.send_worker_event("sid", "w", "s", "ok", "out")
        await client.aclose()

    @pytest.mark.asyncio
    async def test_201_success(self):
        client = make_client(make_handler(201))
        await client.send_worker_event("sid", "w", "s", "ok", "out")
        await client.aclose()

    @pytest.mark.asyncio
    async def test_401_raises_terminal(self):
        client = make_client(make_handler(401))
        with pytest.raises(CMATerminalError) as exc_info:
            await client.send_worker_event("sid", "w", "s", "ok", "out")
        assert exc_info.value.status_code == 401
        await client.aclose()

    @pytest.mark.asyncio
    async def test_403_raises_terminal(self):
        client = make_client(make_handler(403))
        with pytest.raises(CMATerminalError) as exc_info:
            await client.send_worker_event("sid", "w", "s", "ok", "out")
        assert exc_info.value.status_code == 403
        await client.aclose()

    @pytest.mark.asyncio
    async def test_404_raises_terminal(self):
        client = make_client(make_handler(404))
        with pytest.raises(CMATerminalError) as exc_info:
            await client.send_worker_event("sid", "w", "s", "ok", "out")
        assert exc_info.value.status_code == 404
        await client.aclose()

    @pytest.mark.asyncio
    async def test_500_raises_retryable(self):
        client = make_client(make_handler(500))
        with pytest.raises(CMARetryableError) as exc_info:
            await client.send_worker_event("sid", "w", "s", "ok", "out")
        assert exc_info.value.status_code == 500
        await client.aclose()

    @pytest.mark.asyncio
    async def test_502_raises_retryable(self):
        client = make_client(make_handler(502))
        with pytest.raises(CMARetryableError) as exc_info:
            await client.send_worker_event("sid", "w", "s", "ok", "out")
        assert exc_info.value.status_code == 502
        await client.aclose()

    @pytest.mark.asyncio
    async def test_transport_error_raises_retryable_with_status_0(self):
        client = make_client(make_transport_error_handler())
        with pytest.raises(CMARetryableError) as exc_info:
            await client.send_worker_event("sid", "w", "s", "ok", "out")
        assert exc_info.value.status_code == 0
        await client.aclose()


# ---------------------------------------------------------------------------
# aclose
# ---------------------------------------------------------------------------


class TestAclose:
    @pytest.mark.asyncio
    async def test_aclose_works_without_error(self):
        client = make_client(make_handler(200))
        await client.aclose()
