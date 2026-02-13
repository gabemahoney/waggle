CREATE TABLE IF NOT EXISTS state (
    key TEXT PRIMARY KEY,
    repo TEXT NOT NULL,
    status TEXT NOT NULL,
    updated_at TIMESTAMP
);
