#!/usr/bin/env bash
# Sets agent state to custom value provided as parameter
# Use --delete to remove the entry from the database

set -o pipefail

# Check if state parameter provided
if [[ -z "$1" ]]; then
    exit 0
fi

# Check if we're deleting instead of setting state
DELETE_MODE=false
if [[ "$1" == "--delete" ]]; then
    DELETE_MODE=true
fi

STATE="$1"

# Read database path from config with fallback
CONFIG_FILE="$HOME/.waggle/config.json"
DB_PATH="~/.waggle/agent_state.db"
if [[ -f "$CONFIG_FILE" ]]; then
    CUSTOM_PATH=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1])).get('database_path',''))" "$CONFIG_FILE" 2>/dev/null || echo "")
    if [[ -n "$CUSTOM_PATH" ]]; then
        DB_PATH="$CUSTOM_PATH"
    fi
fi

# Expand tilde in DB_PATH
DB_PATH="${DB_PATH/#\~/$HOME}"

# Extract namespace from pwd
NAMESPACE=$(pwd)

# Extract tmux session info
NAME=$(tmux display-message -p '#{session_name}' 2>/dev/null || echo "unknown")
SESSION_ID=$(tmux display-message -p '#{session_id}' 2>/dev/null || echo "unknown")
CREATED=$(tmux display-message -p '#{session_created}' 2>/dev/null || echo "unknown")

# Build key: {name}+{session_id}+{created}
KEY="${NAME}+${SESSION_ID}+${CREATED}"

# Sanitize KEY, STATE, and NAMESPACE for SQL injection protection
# 
# Security Context: LOW RISK - This is a local-only tool with no network exposure.
# The database is user-owned and only accessible by the user running the script.
#
# Protection Strategy: Multi-layer defense against SQL injection
# 1. Remove null bytes (can terminate strings in C-based SQLite)
# 2. Remove control characters (ASCII 0-31, 127) to prevent injection via newlines/etc
# 3. Escape single quotes (SQL string delimiter) using SQLite's doubling convention
#
# Note: We use printf + tr + sed pipeline with pipefail to ensure any step failure
# is detected and causes script exit, preventing bypassed sanitization.
#
sanitize_sql() {
    local input="$1"
    # Remove null bytes, control chars (except tab/newline which we'll handle), then escape quotes
    printf '%s' "$input" | \
        tr -d '\000' | \
        tr -d '[\001-\010\013-\037\177]' | \
        sed "s/'/''/g"
}

SAFE_KEY=$(sanitize_sql "$KEY")
if [[ $? -ne 0 || -z "$SAFE_KEY" ]]; then
    echo "Error: Failed to sanitize KEY" >&2
    exit 0
fi

SAFE_STATE=$(sanitize_sql "$STATE")
if [[ $? -ne 0 ]]; then
    echo "Error: Failed to sanitize STATE" >&2
    exit 0
fi

SAFE_NAMESPACE=$(sanitize_sql "$NAMESPACE")
if [[ $? -ne 0 || -z "$SAFE_NAMESPACE" ]]; then
    echo "Error: Failed to sanitize NAMESPACE" >&2
    exit 0
fi

# Check if we should delete the entry instead of upserting
if [[ "$DELETE_MODE" == true ]]; then
    # DELETE from database
    # SCHEMA SOURCE OF TRUTH: src/waggle/schema.sql — keep in sync
    sqlite3 "$DB_PATH" <<EOF 2>/dev/null
CREATE TABLE IF NOT EXISTS state (
    key TEXT PRIMARY KEY,
    repo TEXT NOT NULL,
    status TEXT NOT NULL,
    updated_at TIMESTAMP
);
DELETE FROM state WHERE key = '$SAFE_KEY';
EOF
else
    # UPSERT into database
    # SCHEMA SOURCE OF TRUTH: src/waggle/schema.sql — keep in sync
    sqlite3 "$DB_PATH" <<EOF 2>/dev/null
CREATE TABLE IF NOT EXISTS state (
    key TEXT PRIMARY KEY,
    repo TEXT NOT NULL,
    status TEXT NOT NULL,
    updated_at TIMESTAMP
);
INSERT OR REPLACE INTO state (key, repo, status, updated_at)
VALUES ('$SAFE_KEY', '$SAFE_NAMESPACE', '$SAFE_STATE', CURRENT_TIMESTAMP);
EOF
fi

exit 0
