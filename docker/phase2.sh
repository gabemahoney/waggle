#!/bin/bash
# phase2.sh — Phase 2 MCP integration test runner inside waggle-ci-2
set -euo pipefail

echo "=== WAGGLE CI PHASE 2 ==="

# Bypass Claude onboarding
mkdir -p "${HOME}/.claude"
cat > "${HOME}/.claude.json" <<'CLAUDEJSON'
{"numStartups":100,"hasCompletedOnboarding":true,"mcpServers":{},"projects":{"/opt/waggle":{"hasTrustDialogAccepted":true}}}
CLAUDEJSON

# Set up waggle hooks in settings.json so hooks fire during tests
mkdir -p "${HOME}/.claude"
cat > "${HOME}/.claude/settings.json" <<'SETTINGS'
{
  "hooks": {
    "SessionStart": [{"hooks": [{"type": "command", "command": "~/.waggle/hooks/waggle_set_state.sh waiting"}]}],
    "UserPromptSubmit": [{"hooks": [{"type": "command", "command": "~/.waggle/hooks/waggle_set_state.sh working"}]}],
    "PreToolUse": [
      {"matcher": "AskUserQuestion", "hooks": [{"type": "command", "command": "~/.waggle/hooks/waggle_set_state.sh waiting"}]},
      {"matcher": "^(?!AskUserQuestion$).*", "hooks": [{"type": "command", "command": "~/.waggle/hooks/waggle_set_state.sh working"}]}
    ],
    "PostToolUse": [{"hooks": [{"type": "command", "command": "~/.waggle/hooks/waggle_set_state.sh working"}]}],
    "PermissionRequest": [{"matcher": "*", "hooks": [{"type": "command", "command": "~/.waggle/hooks/waggle_set_state.sh waiting"}]}],
    "Stop": [{"hooks": [{"type": "command", "command": "~/.waggle/hooks/waggle_set_state.sh waiting"}]}],
    "Notification": [{"matcher": "*", "hooks": [{"type": "command", "command": "~/.waggle/hooks/waggle_set_state.sh waiting"}]}],
    "SessionEnd": [{"hooks": [{"type": "command", "command": "~/.waggle/hooks/waggle_set_state.sh --delete"}]}]
  }
}
SETTINGS

# Install waggle (runs poetry install + registers waggle MCP)
echo "--- Running install.sh ---"
/opt/waggle/install.sh

# Set up testplans hive from read-only mount
echo "--- Setting up testplans hive ---"
export TESTPLANS_CONFIG=/tmp/testplans-config.json
mkdir -p /tmp/testplans

# Write bees config pointing to local writable copy
cat > "${TESTPLANS_CONFIG}" <<'BEESCONFIG'
{
  "schema_version": "2.0",
  "scopes": {
    "/opt/waggle/**": {
      "hives": {
        "testplans": {
          "path": "/tmp/testplans",
          "display_name": "Testplans",
          "created_at": "2026-03-12T00:00:00",
          "child_tiers": {}
        }
      },
      "child_tiers": {}
    }
  }
}
BEESCONFIG

# Copy ticket files from read-only host mount to writable local dir
cp -r /tmp/testplans_host/. /tmp/testplans/

# Register bees MCP with isolated testplans config
echo "--- Registering bees MCP ---"
claude mcp add bees -- bees serve --stdio --config "${TESTPLANS_CONFIG}"

echo "--- Verifying MCP servers ---"
claude mcp list

# Start auto_approve.sh in background
echo "--- Starting auto_approve.sh ---"
/opt/waggle/docker/auto_approve.sh ci > /tmp/auto_approve.log 2>&1 &

# Launch release-test skill in tmux session 'ci'
echo "--- Launching release-test ---"
exec claude "/release-test"
