"""Canonical constants for Claude Spawn test fixtures.

All values conform to the Claude Status consumer-CLI contract 1.0.0.
No logic, no side effects, no external imports.
"""

# ---------------------------------------------------------------------------
# Worker JSON dicts — one per distinct shape the test suite asserts on.
# Required keys: instance_id, status, labels, pending (+ full contract fields)
# ---------------------------------------------------------------------------

WORKER_WORKING = {
    "instance_id": "inst-working-001",
    "status": "working",
    "host": "test-host",
    "cwd": "/work/repo",
    "transcript_path": None,
    "started_at": "2026-05-14T10:00:00.000000000Z",
    "last_seen_at": "2026-05-14T10:05:00.000000000Z",
    "ended_at": None,
    "labels": {
        "claude_spawn_owned": "1",
        "claude_spawn_session_name": "worker-abc",
        "claude_spawn_model": "claude-opus-4-5",
        "claude_spawn_repo": "/work/repo",
    },
    "pending": None,
}

WORKER_ASK_USER_SINGLE = {
    "instance_id": "inst-ask-single-002",
    "status": "ask_user",
    "host": "test-host",
    "cwd": "/work/repo",
    "transcript_path": None,
    "started_at": "2026-05-14T10:00:00.000000000Z",
    "last_seen_at": "2026-05-14T10:06:00.000000000Z",
    "ended_at": None,
    "labels": {
        "claude_spawn_owned": "1",
        "claude_spawn_session_name": "worker-def",
        "claude_spawn_model": "claude-opus-4-5",
        "claude_spawn_repo": "/work/repo",
    },
    "pending": {
        "kind": "ask_user_question",
        "request_id": 7,
        "recorded_at": "2026-05-14T10:06:00.000000000Z",
        "payload_recorded_at": "2026-05-14T10:06:00.000000000Z",
        "tool_name": "AskUserQuestion",
        "tool_input": {
            "questions": [
                {
                    "question": "Should I proceed with the refactor?",
                    "options": None,
                    "multiSelect": False,
                }
            ]
        },
    },
}

WORKER_ASK_USER_MULTI = {
    "instance_id": "inst-ask-multi-003",
    "status": "ask_user",
    "host": "test-host",
    "cwd": "/work/repo",
    "transcript_path": None,
    "started_at": "2026-05-14T10:00:00.000000000Z",
    "last_seen_at": "2026-05-14T10:07:00.000000000Z",
    "ended_at": None,
    "labels": {
        "claude_spawn_owned": "1",
        "claude_spawn_session_name": "worker-ghi",
        "claude_spawn_model": "claude-opus-4-5",
        "claude_spawn_repo": "/work/repo",
    },
    "pending": {
        "kind": "ask_user_question",
        "request_id": 12,
        "recorded_at": "2026-05-14T10:07:00.000000000Z",
        "payload_recorded_at": "2026-05-14T10:07:00.000000000Z",
        "tool_name": "AskUserQuestion",
        "tool_input": {
            "questions": [
                {
                    "question": "Which database engine should I use?",
                    "options": ["sqlite", "postgres"],
                    "multiSelect": False,
                },
                {
                    "question": "Should I add an index?",
                    "options": None,
                    "multiSelect": False,
                },
            ]
        },
    },
}

WORKER_ENDED = {
    "instance_id": "inst-ended-004",
    "status": "ended",
    "host": "test-host",
    "cwd": "/work/repo",
    "transcript_path": "/tmp/transcript-004.json",
    "started_at": "2026-05-14T09:00:00.000000000Z",
    "last_seen_at": "2026-05-14T09:30:00.000000000Z",
    "ended_at": "2026-05-14T09:30:00.000000000Z",
    "labels": {
        "claude_spawn_owned": "1",
        "claude_spawn_session_name": "worker-jkl",
        "claude_spawn_model": "claude-opus-4-5",
        "claude_spawn_repo": "/work/repo",
    },
    "pending": None,
}

# Worker whose labels field is malformed — would appear in the skipped[] array
# of a workers response rather than the workers[] array.
WORKER_MALFORMED_LABELS = {
    "instance_id": "inst-malformed-005",
    "status": "working",
    "host": "test-host",
    "cwd": "/work/repo",
    "transcript_path": None,
    "started_at": "2026-05-14T10:00:00.000000000Z",
    "last_seen_at": "2026-05-14T10:08:00.000000000Z",
    "ended_at": None,
    "labels": {"__malformed__": "\x00invalid\x00"},
    "pending": None,
}

# ---------------------------------------------------------------------------
# Pending-payload dicts (shape of the Worker record's "pending" field)
# ---------------------------------------------------------------------------

PENDING_PERMISSION_REQUEST = {
    "kind": "permission_request",
    "request_id": 42,
    "recorded_at": "2026-05-14T10:05:30.000000000Z",
    "payload_recorded_at": "2026-05-14T10:05:30.000000000Z",
    "tool_name": "Bash",
    "tool_input": {"command": "rm -rf /tmp/test"},
}

PENDING_ASK_USER_SINGLE = {
    "kind": "ask_user_question",
    "request_id": 7,
    "recorded_at": "2026-05-14T10:06:00.000000000Z",
    "payload_recorded_at": "2026-05-14T10:06:00.000000000Z",
    "tool_name": "AskUserQuestion",
    "tool_input": {
        "questions": [
            {
                "question": "Should I proceed with the refactor?",
                "options": None,
                "multiSelect": False,
            }
        ]
    },
}

# Two-question variant — used by SR-3.5 multi-question refusal test in Epic 4.
PENDING_ASK_USER_MULTI = {
    "kind": "ask_user_question",
    "request_id": 12,
    "recorded_at": "2026-05-14T10:07:00.000000000Z",
    "payload_recorded_at": "2026-05-14T10:07:00.000000000Z",
    "tool_name": "AskUserQuestion",
    "tool_input": {
        "questions": [
            {
                "question": "Which database engine should I use?",
                "options": ["sqlite", "postgres"],
                "multiSelect": False,
            },
            {
                "question": "Should I add an index?",
                "options": None,
                "multiSelect": False,
            },
        ]
    },
}

# ---------------------------------------------------------------------------
# Capabilities response dicts (output of `claude-status capabilities`)
# ---------------------------------------------------------------------------

CAPABILITIES_V1 = {
    "contract_version": "1.0.0",
    "stderr_error_grammar": {
        "format": "ERROR: <ErrName>: <description>\\n",
        "trailing_newline": True,
        "err_name_regex": "^[A-Z][A-Za-z0-9]*$",
    },
    "subcommands": [
        {"name": "capabilities"},
        {"name": "decide"},
        {"name": "worker"},
        {"name": "workers"},
    ],
    "typed_errors": [
        "ErrInstanceNotFound",
        "ErrInternal",
        "ErrInvalidLabelFilter",
        "ErrInvalidRequestID",
        "ErrInvalidVerdict",
        "ErrNoPendingRequest",
        "ErrPayloadMalformed",
        "ErrRequestChanged",
        "ErrSchemaMismatch",
        "ErrStoreUnavailable",
        "ErrUnknownPendingKind",
        "ErrUsage",
        "ErrWrongRequestType",
    ],
}

CAPABILITIES_V2 = {
    "contract_version": "2.0.0",
    "stderr_error_grammar": {
        "format": "ERROR: <ErrName>: <description>\\n",
        "trailing_newline": True,
        "err_name_regex": "^[A-Z][A-Za-z0-9]*$",
    },
    "subcommands": [],
    "typed_errors": [],
}

# ---------------------------------------------------------------------------
# Stderr envelope strings — grammar: ERROR: <ErrName>: <description>\n
# ---------------------------------------------------------------------------

STDERR_ERR_INSTANCE_NOT_FOUND = (
    "ERROR: ErrInstanceNotFound: no instance with instance_id=\"inst-missing\"\n"
)

STDERR_ERR_NO_PENDING_REQUEST = (
    "ERROR: ErrNoPendingRequest: no pending permission_request for instance \"inst-working-001\"\n"
)

STDERR_ERR_SCHEMA_MISMATCH = (
    "ERROR: ErrSchemaMismatch: database schema version does not match binary\n"
)

STDERR_ERR_STORE_UNAVAILABLE = (
    "ERROR: ErrStoreUnavailable: cannot open database: no such file or directory\n"
)

STDERR_ERR_PAYLOAD_MALFORMED = (
    "ERROR: ErrPayloadMalformed: instances.labels failed validation: invalid UTF-8\n"
)
