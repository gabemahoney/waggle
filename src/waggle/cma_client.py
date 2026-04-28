"""CMA API async HTTP client for waggle worker event delivery."""

import httpx

_DEFAULT_BASE_URL = "https://api.anthropic.com"
_ANTHROPIC_VERSION = "2023-06-01"
_ANTHROPIC_BETA = "managed-agents-2026-04-01"


class CMATerminalError(Exception):
    def __init__(self, status_code: int, body: str) -> None:
        self.status_code = status_code
        self.body = body
        super().__init__(f"CMA terminal error {status_code}: {body}")


class CMARetryableError(Exception):
    def __init__(self, status_code: int, body: str) -> None:
        self.status_code = status_code
        self.body = body
        super().__init__(f"CMA retryable error {status_code}: {body}")


class CMAClient:
    def __init__(
        self,
        api_key: str,
        base_url: str = _DEFAULT_BASE_URL,
        timeout: float = 30.0,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=timeout,
            headers={
                "x-api-key": api_key,
                "anthropic-version": _ANTHROPIC_VERSION,
                "anthropic-beta": _ANTHROPIC_BETA,
            },
        )

    async def send_worker_event(
        self,
        cma_session_id: str,
        worker_id: str,
        session_name: str,
        status: str,
        output: str,
        pending_relay: dict | None = None,
    ) -> None:
        parts = [f"[system] Worker {worker_id} ({session_name}) is now {status}.", "", output]
        if pending_relay:
            relay_type = pending_relay.get("relay_type", "unknown")
            details = pending_relay.get("details", "")
            parts += ["", f"Permission request ({relay_type}): {details}"]
        text = "\n".join(parts)
        body = {
            "events": [
                {
                    "type": "user.message",
                    "content": [{"type": "text", "text": text}],
                }
            ]
        }
        try:
            response = await self._client.post(
                f"/v1/sessions/{cma_session_id}/events",
                json=body,
            )
        except httpx.TransportError as exc:
            raise CMARetryableError(0, str(exc)) from exc

        if response.is_success:
            return
        sc = response.status_code
        if sc in (401, 403, 404):
            raise CMATerminalError(sc, response.text)
        raise CMARetryableError(sc, response.text)

    async def aclose(self) -> None:
        await self._client.aclose()
