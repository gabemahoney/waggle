PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS workers (
    worker_id      TEXT PRIMARY KEY,
    caller_id      TEXT NOT NULL,
    session_name   TEXT NOT NULL,
    session_id     TEXT NOT NULL,
    model          TEXT NOT NULL,
    repo           TEXT NOT NULL,
    status         TEXT NOT NULL DEFAULT 'working',
    output         TEXT DEFAULT '',
    mcp_session_id TEXT,
    created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_workers_caller ON workers(caller_id);

CREATE TABLE IF NOT EXISTS callers (
    caller_id      TEXT PRIMARY KEY,
    caller_type    TEXT NOT NULL CHECK(caller_type IN ('cma', 'local')),
    cma_session_id TEXT,
    registered_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS requests (
    request_id   TEXT PRIMARY KEY,
    caller_id    TEXT NOT NULL,
    operation    TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'pending',
    result       TEXT DEFAULT '',
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_requests_caller ON requests(caller_id);

CREATE TABLE IF NOT EXISTS pending_relays (
    relay_id    TEXT PRIMARY KEY,
    worker_id   TEXT NOT NULL,
    relay_type  TEXT NOT NULL CHECK(relay_type IN ('permission', 'ask')),
    details     TEXT NOT NULL,
    response    TEXT,
    status      TEXT NOT NULL DEFAULT 'pending',
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_relays_worker ON pending_relays(worker_id);
