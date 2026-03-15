#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ---------------------------------------------------------------------------
# --uninstall
# ---------------------------------------------------------------------------
if [[ "${1:-}" == "--uninstall" ]]; then
  # Remove MCP server registration
  if command -v claude &>/dev/null; then
    claude mcp remove waggle && echo "Removed waggle MCP server." || echo "Could not remove waggle MCP server (may not have been registered)."
  else
    echo "claude not in PATH — skipping MCP removal."
  fi

  # Remove waggle hooks from ~/.claude/settings.json
  SETTINGS_FILE="$HOME/.claude/settings.json"
  if [[ -f "$SETTINGS_FILE" ]]; then
    python3 - "$SETTINGS_FILE" <<'PYEOF'
import json, sys

path = sys.argv[1]
with open(path) as f:
    cfg = json.load(f)

hooks = cfg.get("hooks", {})
events_to_delete = []
for event, entries in hooks.items():
    filtered = [
        e for e in entries
        if not any(
            "waggle_set_state.sh" in h.get("command", "")
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
# Idempotency gate
# ---------------------------------------------------------------------------
if command -v claude &>/dev/null; then
  if claude mcp list 2>/dev/null | grep -q '\bwaggle\b'; then
    echo "Waggle is already installed."
    exit 0
  fi
fi

# ---------------------------------------------------------------------------
# Poetry install
# ---------------------------------------------------------------------------
if ! command -v poetry &>/dev/null; then
  echo "poetry not found. Install poetry from https://python-poetry.org" >&2
  exit 1
fi

echo "Installing Python dependencies..."
poetry install
echo "Python dependencies installed."

# ---------------------------------------------------------------------------
# MCP registration
# ---------------------------------------------------------------------------
if ! command -v claude &>/dev/null; then
  echo "claude not found. Install Claude CLI from https://docs.anthropic.com/en/docs/claude-code" >&2
  exit 1
fi

echo "Registering waggle MCP server..."
claude mcp add --transport stdio --scope user waggle -- poetry run --directory "$SCRIPT_DIR" waggle serve
echo "Waggle MCP server registered."

# ---------------------------------------------------------------------------
# Hook script deployment
# ---------------------------------------------------------------------------
echo "Deploying hook scripts..."
mkdir -p "$HOME/.waggle/hooks"
cp "$SCRIPT_DIR/hooks/waggle_set_state.sh" "$HOME/.waggle/hooks/waggle_set_state.sh"
chmod +x "$HOME/.waggle/hooks/waggle_set_state.sh"
echo "Hook scripts deployed to ~/.waggle/hooks/."

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

if os.path.exists(path):
    with open(path) as f:
        cfg = json.load(f)
else:
    cfg = {}

# Check if already configured
all_commands = [
    h.get("command", "")
    for entries in cfg.get("hooks", {}).values()
    for e in entries
    for h in e.get("hooks", [])
]
if any("waggle_set_state.sh" in c for c in all_commands):
    print("Hooks already configured.")
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

echo ""
echo "Waggle installation complete. Run 'claude mcp list' to verify."
