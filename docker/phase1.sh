#!/bin/bash
# phase1.sh — Phase 1 verification runner inside the waggle-ci container
set -uo pipefail

EXIT_CODE=0

finish() {
  echo "$EXIT_CODE" > /tmp/waggle_phase_exit
  exit "$EXIT_CODE"
}

echo "=== WAGGLE CI PHASE 1 ==="

# Bypass Claude CLI onboarding wizard (required for non-interactive container)
mkdir -p "${HOME}/.claude"
cat > "${HOME}/.claude.json" <<'EOF'
{"numStartups":100,"hasCompletedOnboarding":true,"mcpServers":{},"projects":{}}
EOF

# SR-6.1: Run install.sh
echo "--- Running install.sh ---"
if ! /opt/waggle/install.sh; then
  echo "FAIL: install.sh exited non-zero" >&2
  EXIT_CODE=1
  finish
fi

# SR-6.2: Verify claude mcp list contains waggle
echo "--- Verifying MCP registration ---"
if ! claude mcp list 2>/dev/null | grep -q waggle; then
  echo "FAIL: 'waggle' not found in 'claude mcp list'" >&2
  EXIT_CODE=1
  finish
fi
echo "  waggle MCP server registered."

# SR-6.3: Verify module import
echo "--- Verifying waggle module import ---"
if ! poetry run --directory /opt/waggle python -c "import waggle.server" 2>/dev/null; then
  echo "FAIL: 'import waggle.server' failed" >&2
  EXIT_CODE=1
  finish
fi
echo "  Module import OK."

# SR-6.3: Verify waggle script in venv bin
echo "--- Verifying waggle script in venv ---"
VENV_PATH=$(poetry env info --directory /opt/waggle --path 2>/dev/null || true)
if [[ -z "$VENV_PATH" || ! -f "$VENV_PATH/bin/waggle" ]]; then
  echo "FAIL: 'waggle' script not found in poetry venv bin" >&2
  EXIT_CODE=1
  finish
fi
echo "  waggle script found in venv."

echo ""
echo "WAGGLE CI PHASE 1 PASSED"
EXIT_CODE=0
finish
