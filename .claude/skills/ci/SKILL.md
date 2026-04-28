# /ci — Waggle CI Pipeline

Run the full waggle CI pipeline in Docker. Validates install.sh correctness (Phase 1) and MCP tool functionality (Phase 2) in a clean environment.

## Instructions

Execute each step below in order using bash commands. Stop immediately on any failure unless a step says otherwise.

### Step 1 — Pre-flight: Docker check

```bash
docker info > /dev/null 2>&1
```

If this fails, print:
```
Start Docker Desktop and retry.
```
And stop.

### Step 2 — Pre-flight: Retrieve Claude API key

```bash
# Check env var first (works on Linux and macOS)
CLAUDE_API_KEY="${ANTHROPIC_API_KEY:-}"

# If not in env, try macOS Keychain
if [[ -z "$CLAUDE_API_KEY" ]]; then
  CLAUDE_API_KEY=$(security find-generic-password -s "Claude Code" -w 2>/dev/null || true)
  if [[ -z "$CLAUDE_API_KEY" ]]; then
    CREDS_JSON=$(security find-generic-password -s "Claude Code-credentials" -w 2>/dev/null || true)
    if [[ -n "$CREDS_JSON" ]]; then
      CLAUDE_API_KEY=$(python3 -c "
import json, sys
d = json.loads(sys.argv[1])
print(d.get('claudeAiOauth', {}).get('accessToken', ''))
" "$CREDS_JSON" 2>/dev/null || true)
    fi
  fi
fi

if [[ -z "$CLAUDE_API_KEY" ]]; then
  echo "No Claude API key found. Set ANTHROPIC_API_KEY or run 'claude /login' on macOS."
  exit 1
fi
```

### Step 3 — Pre-run cleanup

Remove any leftover containers and tmux sessions from previous runs:

```bash
docker rm -f waggle-ci-1 waggle-ci-2 2>/dev/null || true
tmux kill-session -t waggle-ci-1 2>/dev/null || true
tmux kill-session -t waggle-ci-2 2>/dev/null || true
```

### Step 4 — Stage source with rsync

Copy waggle source to a temp directory (this becomes the Docker build context). Resolve the waggle project root dynamically from this skill file's location (`.claude/skills/ci/SKILL.md` → project root is 3 levels up).

```bash
BUILD_CTX=$(mktemp -d)
WAGGLE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
rsync -a \
  --exclude '.git' \
  --exclude '.venv' \
  --exclude '__pycache__' \
  --exclude '*.pyc' \
  --exclude '.pytest_cache' \
  --exclude 'tickets' \
  --exclude 'bugs' \
  "$WAGGLE_ROOT/" "$BUILD_CTX/"
echo "Source staged to: $BUILD_CTX"
```

### Step 5 — Build Docker image

```bash
docker build -f "$WAGGLE_ROOT/docker/Dockerfile" -t waggle-ci "$BUILD_CTX"
echo "Docker image built."
```

### Step 6 — Start Phase 1 container

```bash
docker run -d --name waggle-ci-1 -e ANTHROPIC_API_KEY="$CLAUDE_API_KEY" waggle-ci
```

### Step 7 — Create host tmux session for Phase 1 observation

```bash
tmux new-session -d -s waggle-ci-1 "docker exec -it -u waggle waggle-ci-1 tmux attach -t ci; read"
echo "Attach with: tmux attach -t waggle-ci-1"
```

### Step 8 — Wait for Phase 1 to complete

Poll until the container exits:

```bash
while true; do
  STATUS=$(docker inspect waggle-ci-1 --format '{{.State.Status}}' 2>/dev/null || echo "error")
  if [[ "$STATUS" == "exited" || "$STATUS" == "error" ]]; then
    break
  fi
  sleep 2
done
EXIT_CODE=$(docker inspect waggle-ci-1 --format '{{.State.ExitCode}}' 2>/dev/null || echo "1")
```

### Step 9 — Handle Phase 1 result

If `EXIT_CODE` is not `0`:
```bash
echo "WAGGLE CI PHASE 1 FAILED"
docker logs waggle-ci-1 2>&1 | tail -30
```
Then proceed to cleanup (Step 11) and stop.

If `EXIT_CODE` is `0`:
```bash
echo "WAGGLE CI PHASE 1 PASSED"
```

### Step 10 — Start Phase 2 container

```bash
TESTPLANS_PATH="$WAGGLE_ROOT/tickets/testplans"
docker run -d \
  --name waggle-ci-2 \
  -e ANTHROPIC_API_KEY="$CLAUDE_API_KEY" \
  -e PHASE=2 \
  -v "$TESTPLANS_PATH:/tmp/testplans_host:ro" \
  waggle-ci
```

### Step 11 — Create host tmux session for Phase 2 observation

```bash
tmux new-session -d -s waggle-ci-2 "docker exec -it -u waggle waggle-ci-2 tmux attach -t ci; read"
echo "Attach with: tmux attach -t waggle-ci-2"
```

### Step 12 — Wait for Phase 2 to complete

Poll until the container exits:

```bash
while true; do
  STATUS=$(docker inspect waggle-ci-2 --format '{{.State.Status}}' 2>/dev/null || echo "error")
  if [[ "$STATUS" == "exited" || "$STATUS" == "error" ]]; then
    break
  fi
  sleep 2
done
EXIT_CODE=$(docker inspect waggle-ci-2 --format '{{.State.ExitCode}}' 2>/dev/null || echo "1")
```

### Step 13 — Handle Phase 2 result

If `EXIT_CODE` is not `0`:
```bash
echo "WAGGLE CI PHASE 2 FAILED"
docker logs waggle-ci-2 2>&1 | tail -30
```
Then proceed to cleanup (Step 15) and stop.

If `EXIT_CODE` is `0`:
```bash
echo "WAGGLE CI PHASE 2 PASSED"
```

### Step 14 — Final message

Only after both phases pass:
```bash
echo "All phases passed."
```

### Step 15 — Cleanup

Always run cleanup regardless of success or failure:

```bash
docker rm -f waggle-ci-1 waggle-ci-2 2>/dev/null || true
tmux kill-session -t waggle-ci-1 2>/dev/null || true
tmux kill-session -t waggle-ci-2 2>/dev/null || true
```
