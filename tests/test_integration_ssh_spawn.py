"""Integration test: full SSH-signed spawn flow through real middleware + REST."""

import base64
import hashlib
import json
import subprocess
import tempfile
import time
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from waggle.database import init_schema, get_request


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def ssh_keypair(tmp_path_factory):
    """Generate a real ed25519 keypair for testing."""
    key_dir = tmp_path_factory.mktemp("ssh_keys")
    key_path = key_dir / "id_ed25519"

    subprocess.run(
        ["ssh-keygen", "-t", "ed25519", "-f", str(key_path), "-N", ""],
        check=True,
        capture_output=True,
    )

    pub_key = (key_dir / "id_ed25519.pub").read_text().strip()
    # Get fingerprint
    fp_result = subprocess.run(
        ["ssh-keygen", "-l", "-E", "sha256", "-f", str(key_path)],
        capture_output=True,
        text=True,
        check=True,
    )
    # Output: "256 SHA256:xxxx comment (ED25519)"
    fingerprint = fp_result.stdout.split()[1]  # "SHA256:xxxx"

    return {
        "private_key_path": str(key_path),
        "public_key": pub_key,
        "fingerprint": fingerprint,
        "caller_id": "test-caller",
    }


@pytest.fixture
def authorized_keys_file(tmp_path, ssh_keypair):
    """Write authorized_keys.json with the test keypair."""
    keys_path = tmp_path / "authorized_keys.json"
    data = {
        "keys": [
            {
                "name": ssh_keypair["caller_id"],
                "public_key": ssh_keypair["public_key"],
                "fingerprint": ssh_keypair["fingerprint"],
            }
        ]
    }
    keys_path.write_text(json.dumps(data))
    return str(keys_path)


@pytest.fixture
def test_db(tmp_path):
    """Initialize a real temp SQLite DB."""
    db_path = str(tmp_path / "test.db")
    init_schema(db_path)
    return db_path


@pytest.fixture
def inbound_queue(tmp_path):
    """Real inbound queue backed by tmp_path."""
    from waggle.queue import get_inbound_queue
    queue_path = str(tmp_path / "queue.db")
    q = get_inbound_queue(queue_path)
    yield q
    q.close()


def _sign_payload(payload_str: str, private_key_path: str) -> str:
    """Sign payload string with ssh-keygen -Y sign and return base64 signature."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".sig", delete=False) as sig_out:
        sig_path = sig_out.name

    with tempfile.NamedTemporaryFile(mode="w", suffix=".signers", delete=False) as af:
        # allowed_signers format for signing isn't needed — just need -I
        pass

    try:
        # ssh-keygen -Y sign writes <file>.sig
        payload_path = sig_path + ".payload"
        Path(payload_path).write_text(payload_str)

        result = subprocess.run(
            [
                "ssh-keygen", "-Y", "sign",
                "-f", private_key_path,
                "-n", "waggle",
                payload_path,
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"ssh-keygen sign failed: {result.stderr}")

        sig_file = payload_path + ".sig"
        sig_bytes = Path(sig_file).read_bytes()
        return base64.b64encode(sig_bytes).decode()
    finally:
        Path(sig_path).unlink(missing_ok=True)
        Path(payload_path).unlink(missing_ok=True)
        Path(payload_path + ".sig").unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Integration test
# ---------------------------------------------------------------------------


class TestSSHSignedSpawnFlow:
    def test_spawn_returns_202_and_request_id(
        self,
        ssh_keypair,
        authorized_keys_file,
        test_db,
        inbound_queue,
        tmp_path,
    ):
        """Full flow: sign spawn request → POST /api/v1/workers → 202 + request_id in DB."""
        from waggle.server import create_app
        import waggle.rest as rest_module
        import waggle.config as config_module

        # Wire up real queue and DB
        rest_module.set_inbound_queue(inbound_queue)

        app = create_app()

        # Build request body
        body = json.dumps({"model": "sonnet", "repo": "/tmp/test-repo"})
        method = "POST"
        path = "/api/v1/workers"
        timestamp = str(int(time.time()))

        # Reconstruct signing payload (must match auth.reconstruct_payload)
        body_hash = hashlib.sha256(body.encode()).hexdigest()
        payload_str = f"{method}\n{path}\n{timestamp}\n{body_hash}"

        # Sign with real SSH key
        signature_b64 = _sign_payload(payload_str, ssh_keypair["private_key_path"])

        with patch_config(test_db, authorized_keys_file):
            with patch_tmux():
                client = TestClient(app, raise_server_exceptions=True)
                response = client.post(
                    path,
                    content=body,
                    headers={
                        "Content-Type": "application/json",
                        "X-SSH-Signature": signature_b64,
                        "X-SSH-Key-Id": ssh_keypair["fingerprint"],
                        "X-Timestamp": timestamp,
                    },
                )

        assert response.status_code == 202, response.text
        data = response.json()
        assert "request_id" in data
        request_id = data["request_id"]

        # Verify request row created in DB
        row = get_request(test_db, request_id)
        assert row is not None
        assert row["status"] == "pending"

    def test_missing_auth_headers_returns_401(
        self,
        authorized_keys_file,
        test_db,
        inbound_queue,
    ):
        from waggle.server import create_app
        import waggle.rest as rest_module

        rest_module.set_inbound_queue(inbound_queue)
        app = create_app()

        with patch_config(test_db, authorized_keys_file):
            client = TestClient(app, raise_server_exceptions=True)
            response = client.post(
                "/api/v1/workers",
                json={"model": "sonnet", "repo": "/tmp/test"},
            )

        assert response.status_code == 401

    def test_invalid_signature_returns_401(
        self,
        ssh_keypair,
        authorized_keys_file,
        test_db,
        inbound_queue,
    ):
        from waggle.server import create_app
        import waggle.rest as rest_module

        rest_module.set_inbound_queue(inbound_queue)
        app = create_app()

        fake_sig = base64.b64encode(b"not-a-real-signature").decode()
        timestamp = str(int(time.time()))

        with patch_config(test_db, authorized_keys_file):
            client = TestClient(app, raise_server_exceptions=True)
            response = client.post(
                "/api/v1/workers",
                content=json.dumps({"model": "sonnet", "repo": "/tmp/test"}),
                headers={
                    "Content-Type": "application/json",
                    "X-SSH-Signature": fake_sig,
                    "X-SSH-Key-Id": ssh_keypair["fingerprint"],
                    "X-Timestamp": timestamp,
                },
            )

        assert response.status_code == 401


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


from contextlib import contextmanager
from unittest.mock import patch, AsyncMock, MagicMock


@contextmanager
def patch_config(db_path: str, authorized_keys_path: str):
    """Patch config so tests use temp DB and authorized_keys."""
    cfg = {
        "database_path": db_path,
        "queue_path": db_path,
        "max_workers": 8,
        "authorized_keys_path": authorized_keys_path,
        "http_port": 8422,
        "mcp_worker_port": 8423,
        "state_poll_interval_seconds": 2,
        "output_capture_lines": 50,
        "relay_timeout_seconds": 3600,
        "repos_path": "/tmp/test-repos",
        "admin_email": "",
        "admin_notify_after_retries": 5,
        "max_retry_hours": 72,
        "tls_cert_path": "",
        "tls_key_path": "",
    }
    with patch("waggle.config.get_config", return_value=cfg), \
         patch("waggle.config.get_db_path", return_value=db_path), \
         patch("waggle.middleware.config.get_config", return_value=cfg):
        yield


@contextmanager
def patch_tmux():
    """Patch tmux operations to prevent real tmux calls."""
    with patch("waggle.engine.tmux.clone_or_update_repo_async", new_callable=AsyncMock, return_value="/local/repo"), \
         patch("waggle.engine.tmux.create_session", new_callable=AsyncMock, return_value={"status": "success", "session_id": "$1", "session_name": "test-session", "session_created": "1234567890", "worker_id": "mock-id"}), \
         patch("waggle.engine.tmux.launch_agent_in_pane", new_callable=AsyncMock, return_value={"status": "success"}), \
         patch("waggle.engine.tmux.capture_pane", new_callable=AsyncMock, return_value={"status": "success", "content": "test output"}), \
         patch("waggle.engine.tmux.kill_session", new_callable=AsyncMock, return_value={"status": "success"}):
        yield
