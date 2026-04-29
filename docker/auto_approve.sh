#!/bin/bash
SESSION="${1:?Usage: $0 <tmux-session-name>}"
PANE="${SESSION}:0.0"

# Wait up to 30s for session to appear
for i in $(seq 1 30); do
    if tmux has-session -t "$SESSION" 2>/dev/null; then
        break
    fi
    if [[ $i -eq 30 ]]; then
        echo "Session $SESSION never appeared, exiting..."
        exit 1
    fi
    sleep 1
done

while true; do
    if ! tmux has-session -t "$SESSION" 2>/dev/null; then
        exit 0
    fi

    content=$(tmux capture-pane -t "$PANE" -p 2>/dev/null || true)

    # Bypass Permissions safety prompt: select "2. Yes, I accept"
    if echo "$content" | grep -q "Bypass Permissions mode"; then
        tmux send-keys -t "$PANE" "2" Enter
        echo "[$SESSION] $(date +%H:%M:%S) APPROVED: bypass-permissions prompt"
        sleep 1
        continue
    fi

    # API key detection prompt: select "1. Yes" to accept the key
    if echo "$content" | grep -q "Do you want to use this API key"; then
        tmux send-keys -t "$PANE" "1" Enter
        echo "[$SESSION] $(date +%H:%M:%S) APPROVED: api-key prompt"
        sleep 1
        continue
    fi

    # Standard permission prompts: select "2" for session-wide approve
    if echo "$content" | grep -qE "Do you want to (proceed|make|create)\b"; then
        tmux send-keys -t "$PANE" "2" Enter
        echo "[$SESSION] $(date +%H:%M:%S) APPROVED (session-wide): permission prompt"
        sleep 1
        continue
    fi

    # Generic "Do you want to" catch-all: approve with "1"
    if echo "$content" | grep -q "Do you want to"; then
        tmux send-keys -t "$PANE" "1" Enter
        echo "[$SESSION] $(date +%H:%M:%S) APPROVED: generic prompt"
        sleep 1
        continue
    fi

    # "Enter to confirm" without a preceding recognized prompt
    if echo "$content" | grep -q "Enter to confirm"; then
        tmux send-keys -t "$PANE" Enter
        echo "[$SESSION] $(date +%H:%M:%S) APPROVED: enter-to-confirm"
        sleep 1
        continue
    fi

    sleep 1
done
