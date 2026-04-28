"""Tests for waggle.auth — SSH key verification, payload reconstruction, timestamp checking."""

import base64
import hashlib
import json
import subprocess
import time
from pathlib import Path

import pytest

from waggle import auth


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def keypair(tmp_path_factory):
    """Generate a real ed25519 keypair for the module. Returns dict with
    key_path, pub_path, public_key, fingerprint, caller_id.
    """
    d = tmp_path_factory.mktemp("keys")
    key_path = d / "test_key"
    subprocess.run(
        ["ssh-keygen", "-t", "ed25519", "-f", str(key_path), "-N", ""],
        check=True,
        capture_output=True,
    )
    pub_path = Path(str(key_path) + ".pub")
    public_key = pub_path.read_text().strip()

    # Extract fingerprint: "256 SHA256:XXXX comment (ED25519)"
    fp_result = subprocess.run(
        ["ssh-keygen", "-lf", str(pub_path)],
        capture_output=True,
        text=True,
        check=True,
    )
    fingerprint = fp_result.stdout.split()[1]  # e.g. "SHA256:XXXX"

    return {
        "key_path": key_path,
        "pub_path": pub_path,
        "public_key": public_key,
        "fingerprint": fingerprint,
        "caller_id": "test-caller",
    }


@pytest.fixture(scope="module")
def other_keypair(tmp_path_factory):
    """A second keypair that is NOT in authorized_keys."""
    d = tmp_path_factory.mktemp("other_keys")
    key_path = d / "other_key"
    subprocess.run(
        ["ssh-keygen", "-t", "ed25519", "-f", str(key_path), "-N", ""],
        check=True,
        capture_output=True,
    )
    return {"key_path": key_path}


def _sign_payload(key_path: Path, payload: str, tmp_path: Path) -> str:
    """Sign payload with ssh-keygen and return base64-encoded armored signature."""
    payload_file = tmp_path / "payload.txt"
    payload_file.write_text(payload)
    subprocess.run(
        ["ssh-keygen", "-Y", "sign", "-f", str(key_path), "-n", "waggle", str(payload_file)],
        check=True,
        capture_output=True,
    )
    sig_file = Path(str(payload_file) + ".sig")
    armored = sig_file.read_text()
    return base64.b64encode(armored.encode()).decode()


# ---------------------------------------------------------------------------
# load_authorized_keys
# ---------------------------------------------------------------------------


class TestLoadAuthorizedKeys:
    def test_valid_file_returns_keys(self, tmp_path):
        keys_data = {
            "keys": [
                {"name": "caller-a", "public_key": "ssh-ed25519 AAAA...", "fingerprint": "SHA256:abc"},
                {"name": "caller-b", "public_key": "ssh-ed25519 BBBB...", "fingerprint": "SHA256:def"},
            ]
        }
        p = tmp_path / "authorized_keys.json"
        p.write_text(json.dumps(keys_data))
        result = auth.load_authorized_keys(str(p))
        assert len(result) == 2
        assert result[0]["name"] == "caller-a"
        assert result[1]["name"] == "caller-b"

    def test_missing_file_returns_empty(self, tmp_path):
        result = auth.load_authorized_keys(str(tmp_path / "nonexistent.json"))
        assert result == []

    def test_malformed_json_returns_empty(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text("{not valid json")
        result = auth.load_authorized_keys(str(p))
        assert result == []

    def test_empty_keys_list(self, tmp_path):
        p = tmp_path / "empty_keys.json"
        p.write_text(json.dumps({"keys": []}))
        result = auth.load_authorized_keys(str(p))
        assert result == []

    def test_missing_keys_field_returns_empty(self, tmp_path):
        p = tmp_path / "no_keys_field.json"
        p.write_text(json.dumps({"other": "data"}))
        result = auth.load_authorized_keys(str(p))
        assert result == []


# ---------------------------------------------------------------------------
# reconstruct_payload
# ---------------------------------------------------------------------------


class TestReconstructPayload:
    def test_format_is_method_path_timestamp_hash(self):
        method = "POST"
        path = "/api/v1/workers"
        timestamp = "1700000000"
        body = '{"model": "sonnet"}'
        result = auth.reconstruct_payload(method, path, timestamp, body)
        expected_hash = hashlib.sha256(body.encode()).hexdigest()
        assert result == f"{method}\n{path}\n{timestamp}\n{expected_hash}"

    def test_body_hash_is_sha256_hex_digest(self):
        body = "hello world"
        result = auth.reconstruct_payload("GET", "/api/v1/workers", "123", body)
        expected_hash = hashlib.sha256(b"hello world").hexdigest()
        assert result.split("\n")[3] == expected_hash

    def test_empty_body_hashed(self):
        result = auth.reconstruct_payload("GET", "/api/v1/workers", "0", "")
        empty_hash = hashlib.sha256(b"").hexdigest()
        assert result.endswith(empty_hash)

    def test_different_bodies_produce_different_payloads(self):
        p1 = auth.reconstruct_payload("POST", "/api/v1/workers", "1", "body1")
        p2 = auth.reconstruct_payload("POST", "/api/v1/workers", "1", "body2")
        assert p1 != p2


# ---------------------------------------------------------------------------
# check_timestamp
# ---------------------------------------------------------------------------


class TestCheckTimestamp:
    def test_current_time_is_valid(self):
        ts = str(int(time.time()))
        assert auth.check_timestamp(ts) is True

    def test_299s_ago_is_valid(self):
        ts = str(int(time.time()) - 299)
        assert auth.check_timestamp(ts) is True

    def test_301s_ago_is_invalid(self):
        ts = str(int(time.time()) - 301)
        assert auth.check_timestamp(ts) is False

    def test_invalid_string_returns_false(self):
        assert auth.check_timestamp("not-a-timestamp") is False

    def test_empty_string_returns_false(self):
        assert auth.check_timestamp("") is False

    def test_future_timestamp_within_window_is_valid(self):
        # Small clock drift forward is OK
        ts = str(int(time.time()) + 10)
        assert auth.check_timestamp(ts) is True

    def test_far_future_timestamp_is_invalid(self):
        ts = str(int(time.time()) + 400)
        assert auth.check_timestamp(ts) is False


# ---------------------------------------------------------------------------
# verify_ssh_signature
# ---------------------------------------------------------------------------


class TestVerifySSHSignature:
    def _make_authorized_keys(self, keypair):
        return [
            {
                "name": keypair["caller_id"],
                "public_key": keypair["public_key"],
                "fingerprint": keypair["fingerprint"],
            }
        ]

    def test_valid_signature_returns_caller_id(self, keypair, tmp_path):
        payload = "POST\n/api/v1/workers\n1700000000\nabc123"
        signature = _sign_payload(keypair["key_path"], payload, tmp_path)
        authorized_keys = self._make_authorized_keys(keypair)
        result = auth.verify_ssh_signature(
            payload, signature, keypair["fingerprint"], authorized_keys
        )
        assert result == keypair["caller_id"]

    def test_lookup_by_name_also_works(self, keypair, tmp_path):
        payload = "GET\n/api/v1/workers\n1700000001\ndef456"
        signature = _sign_payload(keypair["key_path"], payload, tmp_path)
        authorized_keys = self._make_authorized_keys(keypair)
        result = auth.verify_ssh_signature(
            payload, signature, keypair["caller_id"], authorized_keys
        )
        assert result == keypair["caller_id"]

    def test_wrong_key_returns_none(self, keypair, other_keypair, tmp_path):
        payload = "POST\n/api/v1/workers\n1700000002\nghi789"
        # Sign with other_keypair but look up with keypair's fingerprint
        signature = _sign_payload(other_keypair["key_path"], payload, tmp_path)
        authorized_keys = self._make_authorized_keys(keypair)
        result = auth.verify_ssh_signature(
            payload, signature, keypair["fingerprint"], authorized_keys
        )
        assert result is None

    def test_wrong_payload_returns_none(self, keypair, tmp_path):
        payload = "POST\n/api/v1/workers\n1700000003\njkl012"
        signature = _sign_payload(keypair["key_path"], payload, tmp_path)
        authorized_keys = self._make_authorized_keys(keypair)
        # Verify with a different payload
        result = auth.verify_ssh_signature(
            "POST\n/api/v1/workers\n1700000003\nDIFFERENT",
            signature,
            keypair["fingerprint"],
            authorized_keys,
        )
        assert result is None

    def test_key_not_in_authorized_keys_returns_none(self, keypair, tmp_path):
        payload = "DELETE\n/api/v1/workers/abc\n1700000004\nmno345"
        signature = _sign_payload(keypair["key_path"], payload, tmp_path)
        # Empty authorized_keys list
        result = auth.verify_ssh_signature(
            payload, signature, keypair["fingerprint"], []
        )
        assert result is None

    def test_garbage_signature_returns_none(self, keypair):
        payload = "GET\n/api/v1/workers\n1700000005\npqr678"
        garbage = base64.b64encode(b"this is not a valid ssh signature").decode()
        authorized_keys = self._make_authorized_keys(keypair)
        result = auth.verify_ssh_signature(
            payload, garbage, keypair["fingerprint"], authorized_keys
        )
        assert result is None
