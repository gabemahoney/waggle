"""SSH auth middleware for waggle REST API."""

from pathlib import Path

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from waggle import auth, config


class SSHAuthMiddleware(BaseHTTPMiddleware):
    """Verify SSH signatures on /api/v1/* requests."""

    async def dispatch(self, request: Request, call_next):
        # Only authenticate /api/v1/* paths
        if not request.url.path.startswith("/api/v1"):
            return await call_next(request)

        # Extract headers
        signature = request.headers.get("x-ssh-signature")
        key_id = request.headers.get("x-ssh-key-id")
        timestamp = request.headers.get("x-timestamp")

        if not all([signature, key_id, timestamp]):
            return JSONResponse(
                {"error": "unauthorized", "message": "Missing authentication headers"},
                status_code=401,
            )

        # Check timestamp
        if not auth.check_timestamp(timestamp):
            return JSONResponse(
                {"error": "unauthorized", "message": "Timestamp expired"},
                status_code=401,
            )

        # Load authorized keys
        cfg = config.get_config()
        keys_path = cfg.get("authorized_keys_path", "~/.waggle/authorized_keys.json")
        authorized_keys = auth.load_authorized_keys(str(Path(keys_path).expanduser()))

        # Reconstruct and verify
        body = (await request.body()).decode()
        payload = auth.reconstruct_payload(
            request.method, request.url.path, timestamp, body
        )
        caller_id = auth.verify_ssh_signature(payload, signature, key_id, authorized_keys)

        if caller_id is None:
            return JSONResponse(
                {"error": "unauthorized", "message": "Invalid signature"},
                status_code=401,
            )

        # Set caller_id for downstream handlers
        request.state.caller_id = caller_id
        return await call_next(request)
