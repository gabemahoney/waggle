#!/bin/bash
# entrypoint.sh — starts Phase 1 in a tmux session
set -euo pipefail

# Read PHASE env var (default: 1)
PHASE="${PHASE:-1}"

case "$PHASE" in
  1)
    exec_script="/usr/local/bin/phase1.sh"
    ;;
  2)
    exec_script="/usr/local/bin/phase2.sh"
    ;;
  *)
    echo "ERROR: Unknown PHASE value: $PHASE (must be 1 or 2)" >&2
    exit 1
    ;;
esac

# Start the phase script in a tmux session named 'ci'
tmux new-session -d -s ci "$exec_script"

# Wait for the session to end
while tmux has-session -t ci 2>/dev/null; do
  sleep 1
done

# Read the exit code written by the phase script
EXIT_CODE=0
if [[ -f /tmp/waggle_phase_exit ]]; then
  EXIT_CODE=$(cat /tmp/waggle_phase_exit)
fi

exit "$EXIT_CODE"
