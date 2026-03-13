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

    # Approve any "Do you want to" prompt with numbered options
    if echo "$content" | grep -q "Do you want to" && echo "$content" | grep -qE "^\s*[12][.)]\s"; then
        tmux send-keys -t "$PANE" "1"
        sleep 0.2
        tmux send-keys -t "$PANE" "Enter"
        echo "[$SESSION] $(date +%H:%M:%S) APPROVED: permission prompt"
    fi

    # Approve edit prompts
    if echo "$content" | grep -q "Do you want to make"; then
        tmux send-keys -t "$PANE" "1"
        sleep 0.2
        tmux send-keys -t "$PANE" "Enter"
        echo "[$SESSION] $(date +%H:%M:%S) APPROVED: edit prompt"
    fi

    # Approve create prompts
    if echo "$content" | grep -q "Do you want to create"; then
        tmux send-keys -t "$PANE" "1"
        sleep 0.2
        tmux send-keys -t "$PANE" "Enter"
        echo "[$SESSION] $(date +%H:%M:%S) APPROVED: create prompt"
    fi

    sleep 3
done
