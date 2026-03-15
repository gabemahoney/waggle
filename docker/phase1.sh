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

# Run integration tests
if ! /opt/waggle/tests/integration.sh; then
  echo "FAIL: integration tests failed" >&2
  EXIT_CODE=1
  finish
fi

echo ""
echo "WAGGLE CI PHASE 1 PASSED"
EXIT_CODE=0
finish
