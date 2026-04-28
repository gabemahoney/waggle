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

# Install dependencies
poetry install --no-interaction

# Run pytest
PYTHONPATH=src poetry run python3 -m pytest tests/ --ignore=tests/spikes -q --tb=short
PYTEST_EXIT=$?

# Exit code 5 means pytest collected 0 tests (e.g. import error silently skipped all)
if [[ "$PYTEST_EXIT" -eq 5 ]]; then
  echo "FAIL: pytest collected 0 tests (possible import error)" >&2
  EXIT_CODE=1
  finish
elif [[ "$PYTEST_EXIT" -ne 0 ]]; then
  echo "FAIL: pytest failed with exit code $PYTEST_EXIT" >&2
  EXIT_CODE=1
  finish
fi

echo ""
echo "WAGGLE CI PHASE 1 PASSED"
EXIT_CODE=0
finish
