"""Tests for waggle.middleware.SSHAuthMiddleware."""

import time
from unittest.mock import patch

import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from waggle.middleware import SSHAuthMiddleware


# ---------------------------------------------------------------------------
# Test app setup
# ---------------------------------------------------------------------------


async def echo_caller(request: Request):
    return JSONResponse({"caller_id": request.state.caller_id})


async def public_endpoint(request: Request):
    return JSONResponse({"status": "ok"})


def _make_app():
    app = Starlette(
        routes=[
            Route("/api/v1/test", echo_caller),
            Route("/public", public_endpoint),
        ]
    )
    app.add_middleware(SSHAuthMiddleware)
    return app


@pytest.fixture
def client():
    return TestClient(_make_app(), raise_server_exceptions=True)


# ---------------------------------------------------------------------------
# Header validation
# ---------------------------------------------------------------------------


class TestMissingHeaders:
    def test_no_headers_returns_401(self, client):
        resp = client.get("/api/v1/test")
        assert resp.status_code == 401

    def test_missing_signature_returns_401(self, client):
        ts = str(int(time.time()))
        resp = client.get(
            "/api/v1/test",
            headers={"x-ssh-key-id": "SHA256:abc", "x-timestamp": ts},
        )
        assert resp.status_code == 401

    def test_missing_key_id_returns_401(self, client):
        ts = str(int(time.time()))
        resp = client.get(
            "/api/v1/test",
            headers={"x-ssh-signature": "garbage", "x-timestamp": ts},
        )
        assert resp.status_code == 401

    def test_missing_timestamp_returns_401(self, client):
        resp = client.get(
            "/api/v1/test",
            headers={"x-ssh-signature": "garbage", "x-ssh-key-id": "SHA256:abc"},
        )
        assert resp.status_code == 401

    def test_error_body_has_expected_keys(self, client):
        resp = client.get("/api/v1/test")
        body = resp.json()
        assert "error" in body
        assert "message" in body


# ---------------------------------------------------------------------------
# Timestamp expiry
# ---------------------------------------------------------------------------


class TestExpiredTimestamp:
    def test_old_timestamp_returns_401(self, client):
        old_ts = str(int(time.time()) - 400)
        resp = client.get(
            "/api/v1/test",
            headers={
                "x-ssh-signature": "garbage",
                "x-ssh-key-id": "SHA256:abc",
                "x-timestamp": old_ts,
            },
        )
        assert resp.status_code == 401

    def test_invalid_timestamp_string_returns_401(self, client):
        resp = client.get(
            "/api/v1/test",
            headers={
                "x-ssh-signature": "garbage",
                "x-ssh-key-id": "SHA256:abc",
                "x-timestamp": "not-a-timestamp",
            },
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Invalid signature
# ---------------------------------------------------------------------------


class TestInvalidSignature:
    def test_garbage_signature_returns_401(self, client):
        import base64
        ts = str(int(time.time()))
        garbage = base64.b64encode(b"not a real signature").decode()
        with patch("waggle.middleware.auth.load_authorized_keys", return_value=[]):
            resp = client.get(
                "/api/v1/test",
                headers={
                    "x-ssh-signature": garbage,
                    "x-ssh-key-id": "SHA256:abc",
                    "x-timestamp": ts,
                },
            )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Valid signature (mocked)
# ---------------------------------------------------------------------------


class TestValidSignature:
    def test_valid_signature_returns_200_with_caller_id(self, client):
        ts = str(int(time.time()))
        with (
            patch("waggle.middleware.auth.load_authorized_keys", return_value=[{"name": "alice", "fingerprint": "SHA256:foo", "public_key": "ssh-ed25519 AAAA..."}]),
            patch("waggle.middleware.auth.verify_ssh_signature", return_value="alice"),
        ):
            resp = client.get(
                "/api/v1/test",
                headers={
                    "x-ssh-signature": "dmFsaWQ=",
                    "x-ssh-key-id": "SHA256:foo",
                    "x-timestamp": ts,
                },
            )
        assert resp.status_code == 200
        assert resp.json()["caller_id"] == "alice"

    def test_caller_id_set_on_request_state(self, client):
        ts = str(int(time.time()))
        with (
            patch("waggle.middleware.auth.load_authorized_keys", return_value=[{"name": "bob", "fingerprint": "SHA256:bar", "public_key": "ssh-ed25519 AAAA..."}]),
            patch("waggle.middleware.auth.verify_ssh_signature", return_value="bob"),
        ):
            resp = client.get(
                "/api/v1/test",
                headers={
                    "x-ssh-signature": "dmFsaWQ=",
                    "x-ssh-key-id": "SHA256:bar",
                    "x-timestamp": ts,
                },
            )
        assert resp.json()["caller_id"] == "bob"


# ---------------------------------------------------------------------------
# Non-API paths bypass auth
# ---------------------------------------------------------------------------


class TestPublicPaths:
    def test_non_api_path_passes_through(self, client):
        resp = client.get("/public")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    def test_non_api_path_requires_no_headers(self, client):
        # Should succeed with no auth headers at all
        resp = client.get("/public")
        assert resp.status_code == 200
