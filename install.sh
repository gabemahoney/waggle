#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ---------------------------------------------------------------------------
# --uninstall
# ---------------------------------------------------------------------------
if [[ "${1:-}" == "--uninstall" ]]; then
  # Stop and disable the systemd service
  if systemctl --user is-active --quiet waggle 2>/dev/null; then
    systemctl --user stop waggle
    echo "Stopped waggle service."
  fi
  if systemctl --user is-enabled --quiet waggle 2>/dev/null; then
    systemctl --user disable waggle
    echo "Disabled waggle service."
  fi

  # Remove the service file
  SERVICE_FILE="$HOME/.config/systemd/user/waggle.service"
  if [[ -f "$SERVICE_FILE" ]]; then
    rm "$SERVICE_FILE"
    echo "Removed $SERVICE_FILE."
  fi

  systemctl --user daemon-reload 2>/dev/null || true

  # Remove waggle hooks from ~/.claude/settings.json
  SETTINGS_FILE="$HOME/.claude/settings.json"
  if [[ -f "$SETTINGS_FILE" ]]; then
    python3 - "$SETTINGS_FILE" <<'PYEOF'
import json, sys

path = sys.argv[1]
with open(path) as f:
    cfg = json.load(f)

hooks = cfg.get("hooks", {})
waggle_commands = {"waggle set-state", "waggle permission-request", "waggle ask-relay"}
events_to_delete = []

for event, entries in hooks.items():
    filtered = [
        e for e in entries
        if not any(
            any(wc in h.get("command", "") for wc in waggle_commands)
            for h in e.get("hooks", [])
        )
    ]
    if filtered:
        hooks[event] = filtered
    else:
        events_to_delete.append(event)

for ev in events_to_delete:
    del hooks[ev]

if hooks:
    cfg["hooks"] = hooks
elif "hooks" in cfg:
    del cfg["hooks"]

with open(path, "w") as f:
    json.dump(cfg, f, indent=2)
    f.write("\n")

print("Removed waggle hooks from ~/.claude/settings.json.")
PYEOF
  else
    echo "~/.claude/settings.json not found — skipping hook removal."
  fi

  echo ""
  echo "Waggle uninstalled. Run the following to complete removal:"
  echo "  claude mcp remove waggle"
  exit 0
fi

# ---------------------------------------------------------------------------
# Verify we're in the right place
# ---------------------------------------------------------------------------
if [[ ! -f "$SCRIPT_DIR/pyproject.toml" ]]; then
  echo "Error: pyproject.toml not found in $SCRIPT_DIR. Run install.sh from the waggle project root." >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Install Python dependencies
# ---------------------------------------------------------------------------
if command -v poetry &>/dev/null; then
  echo "Installing Python dependencies with poetry..."
  poetry install
else
  echo "poetry not found — falling back to pip..."
  pip install -e "$SCRIPT_DIR"
fi
echo "Python dependencies installed."

# ---------------------------------------------------------------------------
# Deploy systemd service
# ---------------------------------------------------------------------------
echo "Deploying waggle.service..."
SYSTEMD_DIR="$HOME/.config/systemd/user"
mkdir -p "$SYSTEMD_DIR"
cp "$SCRIPT_DIR/waggle.service" "$SYSTEMD_DIR/waggle.service"
systemctl --user daemon-reload
systemctl --user enable --now waggle
echo "waggle.service enabled and started."

# ---------------------------------------------------------------------------
# Merge waggle hooks into ~/.claude/settings.json
# ---------------------------------------------------------------------------
echo "Configuring Claude hooks..."
SETTINGS_FILE="$HOME/.claude/settings.json"
mkdir -p "$HOME/.claude"

python3 - "$SETTINGS_FILE" <<'PYEOF'
import json, sys, os

path = sys.argv[1]

waggle_hooks = {
    "PermissionRequest": [{"matcher": "*", "hooks": [{"type": "command", "command": "waggle permission-request"}]}],
    "SessionStart": [{"hooks": [{"type": "command", "command": "waggle set-state waiting"}]}],
    "UserPromptSubmit": [{"hooks": [{"type": "command", "command": "waggle set-state working"}]}],
    "PreToolUse": [
        {"matcher": "AskUserQuestion", "hooks": [{"type": "command", "command": "waggle ask-relay"}]},
        {"matcher": "^(?!AskUserQuestion$).*", "hooks": [{"type": "command", "command": "waggle set-state working"}]}
    ],
    "PostToolUse": [{"hooks": [{"type": "command", "command": "waggle set-state working"}]}],
    "Notification": [{"matcher": "*", "hooks": [{"type": "command", "command": "waggle set-state waiting"}]}],
    "Stop": [{"hooks": [{"type": "command", "command": "waggle set-state waiting"}]}],
    "SessionEnd": [{"hooks": [{"type": "command", "command": "waggle set-state --delete"}]}]
}

if os.path.exists(path):
    with open(path) as f:
        cfg = json.load(f)
else:
    cfg = {}

# Idempotency: skip if waggle hooks already present
waggle_commands = {"waggle set-state", "waggle permission-request", "waggle ask-relay"}
all_commands = [
    h.get("command", "")
    for entries in cfg.get("hooks", {}).values()
    for e in entries
    for h in e.get("hooks", [])
]
if any(any(wc in c for wc in waggle_commands) for c in all_commands):
    print("Waggle hooks already configured — skipping.")
    sys.exit(0)

# Merge
existing_hooks = cfg.get("hooks", {})
for event, entries in waggle_hooks.items():
    existing_hooks.setdefault(event, [])
    existing_hooks[event].extend(entries)
cfg["hooks"] = existing_hooks

with open(path, "w") as f:
    json.dump(cfg, f, indent=2)
    f.write("\n")

print("Claude hooks configured in ~/.claude/settings.json.")
PYEOF

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------
echo ""
echo "Waggle installation complete."
echo ""
echo "Register the MCP server with Claude Code:"
echo "  claude mcp add --transport http waggle http://localhost:8422/mcp"
echo ""
echo "Verify the daemon is running:"
echo "  systemctl --user status waggle"
echo "  curl http://localhost:8422/mcp"
