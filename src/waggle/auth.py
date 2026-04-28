"""SSH key signature verification for waggle REST API."""

import base64
import hashlib
import json
import subprocess
import tempfile
import time
from pathlib import Path


def load_authorized_keys(path: str) -> list[dict]:
    """Load authorized keys from JSON file.

    File format: {"keys": [{"name": "caller-id", "public_key": "ssh-ed25519 AAAA...", "fingerprint": "SHA256:..."}]}
    Returns list of key dicts. Returns empty list if file missing or malformed.
    """
    try:
        with open(path) as f:
            data = json.load(f)
        return data.get("keys", [])
    except (OSError, json.JSONDecodeError):
        return []


def reconstruct_payload(method: str, path: str, timestamp: str, body: str) -> str:
    """Build the signing payload string.

    Format per SRD §8.1: "{method}\n{path}\n{timestamp}\n{SHA256(body)}"
    """
    body_hash = hashlib.sha256(body.encode()).hexdigest()
    return f"{method}\n{path}\n{timestamp}\n{body_hash}"


def check_timestamp(ts_str: str, max_age: int = 300) -> bool:
    """Check if timestamp is within max_age seconds of current time."""
    try:
        ts = int(ts_str)
        return abs(time.time() - ts) <= max_age
    except (ValueError, TypeError):
        return False


def verify_ssh_signature(payload: str, signature: str, key_id: str, authorized_keys: list[dict]) -> str | None:
    """Verify an SSH signature against authorized keys.

    Finds the key matching key_id (by fingerprint or name), writes a temp
    allowed_signers file, and calls ssh-keygen -Y verify.

    Returns caller_id (key name) on success, None on failure.
    """
    # Find matching key
    matching_key = None
    for key in authorized_keys:
        if key.get("fingerprint") == key_id or key.get("name") == key_id:
            matching_key = key
            break

    if matching_key is None:
        return None

    caller_id = matching_key["name"]
    public_key = matching_key["public_key"]

    # ssh-keygen -Y verify needs an allowed_signers file with format:
    # principal_name namespaces="waggle" key_type key_data
    signers_path = None
    sig_path = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".signers", delete=False) as signers_f:
            signers_f.write(f"{caller_id} namespaces=\"waggle\" {public_key}\n")
            signers_path = signers_f.name

        with tempfile.NamedTemporaryFile(mode="w", suffix=".sig", delete=False) as sig_f:
            sig_f.write(base64.b64decode(signature).decode())
            sig_path = sig_f.name

        result = subprocess.run(
            [
                "ssh-keygen", "-Y", "verify",
                "-f", signers_path,
                "-I", caller_id,
                "-n", "waggle",
                "-s", sig_path,
            ],
            input=payload,
            capture_output=True,
            text=True,
            timeout=5,
        )

        if result.returncode == 0:
            return caller_id
        return None
    except Exception:
        return None
    finally:
        # Clean up temp files
        if signers_path:
            Path(signers_path).unlink(missing_ok=True)
        if sig_path:
            Path(sig_path).unlink(missing_ok=True)
