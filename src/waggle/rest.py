"""Waggle v2 REST API route handlers for /api/v1/*."""

import json
import uuid

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route, Router

from waggle import config, database, engine
from waggle.queue import MessageEnvelope, MessageType, enqueue_inbound, get_inbound_queue

# Module-level queue reference (set by daemon on startup)
_inbound_queue = None


def set_inbound_queue(queue):
    global _inbound_queue
    _inbound_queue = queue


_MESSAGES = {
    "worker_not_found": "Worker not found or not owned by caller",
    "no_pending_permission": "No pending permission request for this worker",
    "no_pending_question": "No pending question for this worker",
    "concurrency_limit_reached": "Maximum worker limit reached",
    "request_not_found": "Request not found",
}


def _err(code: str, status: int) -> JSONResponse:
    return JSONResponse(
        {"error": code, "message": _MESSAGES.get(code, code)}, status_code=status
    )


# ---------------------------------------------------------------------------
# Sync endpoints
# ---------------------------------------------------------------------------


async def register(request: Request) -> JSONResponse:
    body = await request.json()
    caller_id = request.state.caller_id
    result = await engine.register_caller(
        caller_id,
        body.get("caller_type", "local"),
        body.get("cma_session_id"),
    )
    return JSONResponse(result)


async def list_workers(request: Request) -> JSONResponse:
    caller_id = request.state.caller_id
    workers = await engine.list_workers(caller_id)
    return JSONResponse({"workers": workers})


async def check_status(request: Request) -> JSONResponse:
    caller_id = request.state.caller_id
    worker_id = request.path_params["id"]
    result = await engine.check_status(caller_id, worker_id)
    if "error" in result:
        return _err(result["error"], 404)
    return JSONResponse(result)


async def get_output(request: Request) -> JSONResponse:
    caller_id = request.state.caller_id
    worker_id = request.path_params["id"]
    scrollback = int(request.query_params.get("scrollback", "200"))
    result = await engine.get_output(caller_id, worker_id, scrollback)
    if "error" in result:
        return _err(result["error"], 404)
    return JSONResponse(result)


async def approve_permission(request: Request) -> JSONResponse:
    caller_id = request.state.caller_id
    worker_id = request.path_params["id"]
    body = await request.json()
    result = await engine.approve_permission(caller_id, worker_id, body["decision"])
    if "error" in result:
        code = 404 if result["error"] in ("worker_not_found", "no_pending_permission") else 400
        return _err(result["error"], code)
    return JSONResponse(result)


async def answer_question(request: Request) -> JSONResponse:
    caller_id = request.state.caller_id
    worker_id = request.path_params["id"]
    body = await request.json()
    result = await engine.answer_question(caller_id, worker_id, body["answer"])
    if "error" in result:
        code = 404 if result["error"] in ("worker_not_found", "no_pending_question") else 400
        return _err(result["error"], code)
    return JSONResponse(result)


async def check_request(request: Request) -> JSONResponse:
    db_path = config.get_db_path()
    request_id = request.path_params["id"]
    result = database.get_request(db_path, request_id)
    if result is None:
        return _err("request_not_found", 404)
    return JSONResponse(result)


# ---------------------------------------------------------------------------
# Async endpoints
# ---------------------------------------------------------------------------


async def spawn_worker(request: Request) -> JSONResponse:
    caller_id = request.state.caller_id
    body = await request.json()
    cfg = config.get_config()
    db_path = config.get_db_path()

    with database.connection(db_path) as conn:
        row = conn.execute("SELECT COUNT(*) FROM workers WHERE status != 'done'").fetchone()
        if row[0] >= int(cfg["max_workers"]):
            return _err("concurrency_limit_reached", 409)

    request_id = str(uuid.uuid4())
    params = json.dumps({
        "caller_id": caller_id,
        "model": body.get("model"),
        "repo": body.get("repo"),
        "session_name": body.get("session_name"),
    })
    database.create_request(db_path, request_id, caller_id, "spawn_worker", params)
    envelope = MessageEnvelope(
        message_type=MessageType.INBOUND,
        caller_id=caller_id,
        payload={
            "operation": "spawn_worker",
            "request_id": request_id,
            "model": body.get("model"),
            "repo": body.get("repo"),
            "session_name": body.get("session_name"),
            "command": body.get("command"),
        },
    )
    enqueue_inbound(_inbound_queue, envelope)
    return JSONResponse({"request_id": request_id}, status_code=202)


async def send_input(request: Request) -> JSONResponse:
    caller_id = request.state.caller_id
    worker_id = request.path_params["id"]
    db_path = config.get_db_path()

    with database.connection(db_path) as conn:
        row = conn.execute(
            "SELECT worker_id FROM workers WHERE worker_id = ? AND caller_id = ?",
            (worker_id, caller_id),
        ).fetchone()

    if row is None:
        return _err("worker_not_found", 404)

    body = await request.json()
    request_id = str(uuid.uuid4())
    params = json.dumps({"worker_id": worker_id, "text": body.get("text")})
    database.create_request(db_path, request_id, caller_id, "send_input", params)
    envelope = MessageEnvelope(
        message_type=MessageType.INBOUND,
        caller_id=caller_id,
        payload={
            "operation": "send_input",
            "request_id": request_id,
            "worker_id": worker_id,
            "text": body.get("text"),
        },
    )
    enqueue_inbound(_inbound_queue, envelope)
    return JSONResponse({"request_id": request_id}, status_code=202)


async def terminate_worker(request: Request) -> JSONResponse:
    caller_id = request.state.caller_id
    worker_id = request.path_params["id"]
    db_path = config.get_db_path()

    with database.connection(db_path) as conn:
        row = conn.execute(
            "SELECT worker_id FROM workers WHERE worker_id = ? AND caller_id = ?",
            (worker_id, caller_id),
        ).fetchone()

    if row is None:
        return _err("worker_not_found", 404)

    request_id = str(uuid.uuid4())
    params = json.dumps({"worker_id": worker_id})
    database.create_request(db_path, request_id, caller_id, "terminate_worker", params)
    envelope = MessageEnvelope(
        message_type=MessageType.INBOUND,
        caller_id=caller_id,
        payload={
            "operation": "terminate_worker",
            "request_id": request_id,
            "worker_id": worker_id,
        },
    )
    enqueue_inbound(_inbound_queue, envelope)
    return JSONResponse({"request_id": request_id}, status_code=202)


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

rest_router = Router(
    routes=[
        Route("/register", register, methods=["POST"]),
        Route("/workers", spawn_worker, methods=["POST"]),
        Route("/workers", list_workers, methods=["GET"]),
        Route("/workers/{id}/status", check_status, methods=["GET"]),
        Route("/workers/{id}/output", get_output, methods=["GET"]),
        Route("/workers/{id}/input", send_input, methods=["POST"]),
        Route("/workers/{id}/approve", approve_permission, methods=["POST"]),
        Route("/workers/{id}/answer", answer_question, methods=["POST"]),
        Route("/workers/{id}", terminate_worker, methods=["DELETE"]),
        Route("/requests/{id}", check_request, methods=["GET"]),
    ]
)
