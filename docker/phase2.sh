#!/bin/bash
# phase2.sh — Phase 2 MCP integration test runner inside waggle-ci-2
set -uo pipefail

EXIT_CODE=0
WAGGLE_PID=0

finish() {
  [[ $WAGGLE_PID -gt 0 ]] && kill $WAGGLE_PID 2>/dev/null || true
  echo "$EXIT_CODE" > /tmp/waggle_phase_exit
  exit "$EXIT_CODE"
}

echo "=== WAGGLE CI PHASE 2 ==="

# Bypass Claude onboarding, write API key to .claude.json
mkdir -p "${HOME}/.claude"
python3 -c "
import json, os
d = {'numStartups': 100, 'hasCompletedOnboarding': True, 'mcpServers': {}, 'projects': {'/opt/waggle': {'hasTrustDialogAccepted': True}}}
key = os.environ.get('ANTHROPIC_API_KEY', '')
if key:
    d['apiKey'] = key
open(os.path.expanduser('~/.claude.json'), 'w').write(json.dumps(d, indent=2))
print('API key written to .claude.json' if key else 'WARNING: No API key found')
"
cat > "${HOME}/.claude/settings.json" <<'SETTINGS'
{
  "enableAllProjectMcpServers": true,
  "hooks": {
    "PermissionRequest": [{"matcher": "*", "hooks": [{"type": "command", "command": "waggle permission-request"}]}],
    "SessionStart": [{"hooks": [{"type": "command", "command": "waggle set-state waiting"}]}],
    "UserPromptSubmit": [{"hooks": [{"type": "command", "command": "waggle set-state working"}]}],
    "PreToolUse": [
      {"matcher": "AskUserQuestion", "hooks": [{"type": "command", "command": "waggle ask-relay"}]},
      {"matcher": "^(?!AskUserQuestion$).*", "hooks": [{"type": "command", "command": "waggle set-state working"}]}
    ],
    "PostToolUse": [{"hooks": [{"type": "command", "command": "waggle set-state working"}]}],
    "Stop": [{"hooks": [{"type": "command", "command": "waggle set-state waiting"}]}],
    "SessionEnd": [{"hooks": [{"type": "command", "command": "waggle set-state --delete"}]}]
  }
}
SETTINGS

# Install waggle deps and start daemon
echo "--- Installing waggle dependencies ---"
cd /opt/waggle
poetry install --no-interaction

# Put venv bin on PATH so hooks can find the waggle CLI
VENV_BIN="$(poetry env info -p)/bin"
export PATH="$VENV_BIN:$PATH"
echo "Venv bin added to PATH: $VENV_BIN"

echo "--- Starting waggle daemon ---"
export WAGGLE_CMA_API_KEY="dummy-ci-key"
PYTHONPATH=src poetry run waggle serve &
WAGGLE_PID=$!

echo "--- Waiting for daemon health check ---"
for i in $(seq 1 20); do
  if curl -sf http://localhost:8422/mcp >/dev/null 2>&1; then
    echo "Daemon is ready."
    break
  fi
  if [[ $i -eq 20 ]]; then
    echo "FAIL: daemon did not respond within 10s" >&2
    EXIT_CODE=1
    finish
  fi
  sleep 0.5
done

# Register waggle MCP via HTTP transport
echo "--- Registering waggle MCP ---"
claude mcp add --transport http waggle http://localhost:8422/mcp

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

# Launch release-test skill — capture exit code for entrypoint.sh
echo "--- Launching release-test ---"
claude -p "/release-test" \
  --allowedTools 'mcp__waggle__*' \
  --allowedTools 'mcp__bees__*' \
  --allowedTools 'Bash(mkdir*)' \
  || EXIT_CODE=$?

if [[ $EXIT_CODE -eq 0 ]]; then
  echo "WAGGLE CI PHASE 2 PASSED"
else
  echo "FAIL: release-test exited with code $EXIT_CODE" >&2
fi

finish
