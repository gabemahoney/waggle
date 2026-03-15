#!/bin/bash
set -uo pipefail

# ============================================================================
# Waggle Integration Test Framework
# ============================================================================

REPO=/opt/waggle
TEST_NUM=0
PASS_COUNT=0
FAIL_COUNT=0
CMD_OUT=""
CMD_ERR=""
CMD_EXIT=0

# ---------- helpers ----------

pass_test() {
    PASS_COUNT=$((PASS_COUNT + 1))
    echo "[PASS] $1"
}

fail_test() {
    FAIL_COUNT=$((FAIL_COUNT + 1))
    echo "[FAIL] $1: $2"
}

run_test() {
    TEST_NUM=$((TEST_NUM + 1))
    "$1"
}

capture_cmd() {
    CMD_OUT=""
    CMD_ERR=""
    CMD_EXIT=0
    CMD_OUT=$("$@" 2>/tmp/_cap_err) || CMD_EXIT=$?
    CMD_ERR=$(cat /tmp/_cap_err)
}

check_json() {
    local json_str="$1"
    local py_expr="$2"
    python3 -c "
import json, sys
data = json.loads(sys.argv[1])
if not ($py_expr):
    sys.exit(1)
" "$json_str" || fail_test "$CURRENT_TEST" "check_json failed: $py_expr"
}

assert_no_traceback() {
    local output="$1"
    local name="$2"
    if echo "$output" | grep -q "Traceback"; then
        fail_test "$name" "Traceback found in output"
    fi
}

assert_eq() {
    local got="$1"
    local expected="$2"
    local name="$3"
    if [[ "$got" != "$expected" ]]; then
        fail_test "$name" "expected '$expected', got '$got'"
    fi
}

assert_contains() {
    local haystack="$1"
    local needle="$2"
    local name="$3"
    if [[ "$haystack" != *"$needle"* ]]; then
        fail_test "$name" "output does not contain '$needle'"
    fi
}

# ============================================================================
# Phase 1 tests (migrated from phase1.sh)
# ============================================================================

test_install_sh_runs() {
    CURRENT_TEST="test_install_sh_runs"
    capture_cmd "$REPO/install.sh"
    assert_eq "$CMD_EXIT" "0" "$CURRENT_TEST"
    pass_test "$CURRENT_TEST"
}

test_mcp_registered() {
    CURRENT_TEST="test_mcp_registered"
    capture_cmd claude mcp list
    assert_contains "$CMD_OUT" "waggle" "$CURRENT_TEST"
    pass_test "$CURRENT_TEST"
}

test_module_import() {
    CURRENT_TEST="test_module_import"
    capture_cmd poetry run --directory "$REPO" python -c "import waggle.server"
    assert_eq "$CMD_EXIT" "0" "$CURRENT_TEST"
    pass_test "$CURRENT_TEST"
}

test_venv_script_exists() {
    CURRENT_TEST="test_venv_script_exists"
    local venv_path
    venv_path=$(poetry env info --directory "$REPO" --path 2>/dev/null || true)
    if [[ -z "$venv_path" || ! -f "$venv_path/bin/waggle" ]]; then
        fail_test "$CURRENT_TEST" "waggle script not found in poetry venv bin"
    fi
    pass_test "$CURRENT_TEST"
}

# ============================================================================
# CLI foundation tests
# ============================================================================

test_waggle_help_exits_0() {
    CURRENT_TEST="test_waggle_help_exits_0"
    capture_cmd poetry run --directory "$REPO" waggle --help
    assert_eq "$CMD_EXIT" "0" "$CURRENT_TEST"
    assert_contains "$CMD_OUT" "serve" "$CURRENT_TEST"
    pass_test "$CURRENT_TEST"
}

test_waggle_no_subcommand_exits_0() {
    CURRENT_TEST="test_waggle_no_subcommand_exits_0"
    capture_cmd poetry run --directory "$REPO" waggle
    assert_eq "$CMD_EXIT" "0" "$CURRENT_TEST"
    pass_test "$CURRENT_TEST"
}

test_waggle_serve_help_exits_0() {
    CURRENT_TEST="test_waggle_serve_help_exits_0"
    capture_cmd poetry run --directory "$REPO" waggle serve --help
    assert_eq "$CMD_EXIT" "0" "$CURRENT_TEST"
    pass_test "$CURRENT_TEST"
}

test_waggle_usage_error_json() {
    CURRENT_TEST="test_waggle_usage_error_json"
    capture_cmd poetry run --directory "$REPO" waggle --unknown-flag-xyz
    assert_eq "$CMD_EXIT" "2" "$CURRENT_TEST"
    assert_contains "$CMD_OUT" '"status"' "$CURRENT_TEST"
    assert_contains "$CMD_OUT" '"error"' "$CURRENT_TEST"
    pass_test "$CURRENT_TEST"
}

# ============================================================================
# Package manager install tests
# ============================================================================

test_pipx_install() {
    CURRENT_TEST="test_pipx_install"
    capture_cmd env PIPX_HOME=/tmp/waggle-pipx-test PIPX_BIN_DIR=/tmp/waggle-pipx-bin pipx install "$REPO" --force
    assert_eq "$CMD_EXIT" "0" "$CURRENT_TEST"
    if [[ ! -f /tmp/waggle-pipx-bin/waggle ]]; then
        fail_test "$CURRENT_TEST" "waggle binary not found in /tmp/waggle-pipx-bin"
    fi
    capture_cmd /tmp/waggle-pipx-bin/waggle --help
    assert_eq "$CMD_EXIT" "0" "$CURRENT_TEST"
    assert_no_traceback "$CMD_OUT" "pipx waggle --help"
    assert_contains "$CMD_OUT" "serve" "pipx waggle output contains serve"
    pass_test "$CURRENT_TEST"
}

test_uv_install() {
    CURRENT_TEST="test_uv_install"
    capture_cmd env UV_TOOL_BIN_DIR=/tmp/waggle-uv-bin uv tool install "$REPO"
    assert_eq "$CMD_EXIT" "0" "$CURRENT_TEST"
    if [[ ! -f /tmp/waggle-uv-bin/waggle ]]; then
        fail_test "$CURRENT_TEST" "waggle binary not found in /tmp/waggle-uv-bin"
    fi
    capture_cmd /tmp/waggle-uv-bin/waggle --help
    assert_eq "$CMD_EXIT" "0" "$CURRENT_TEST"
    assert_no_traceback "$CMD_OUT" "uv waggle --help"
    assert_contains "$CMD_OUT" "serve" "uv waggle output contains serve"
    pass_test "$CURRENT_TEST"
}

# ============================================================================
# Lifecycle subcommand tests
# ============================================================================

test_list_agents_help() {
    CURRENT_TEST="test_list_agents_help"
    capture_cmd poetry run --directory "$REPO" waggle list-agents --help
    assert_eq "$CMD_EXIT" "0" "$CURRENT_TEST"
    pass_test "$CURRENT_TEST"
}

test_spawn_agent_help() {
    CURRENT_TEST="test_spawn_agent_help"
    capture_cmd poetry run --directory "$REPO" waggle spawn-agent --help
    assert_eq "$CMD_EXIT" "0" "$CURRENT_TEST"
    pass_test "$CURRENT_TEST"
}

test_close_session_help() {
    CURRENT_TEST="test_close_session_help"
    capture_cmd poetry run --directory "$REPO" waggle close-session --help
    assert_eq "$CMD_EXIT" "0" "$CURRENT_TEST"
    pass_test "$CURRENT_TEST"
}

test_delete_repo_agents_help() {
    CURRENT_TEST="test_delete_repo_agents_help"
    capture_cmd poetry run --directory "$REPO" waggle delete-repo-agents --help
    assert_eq "$CMD_EXIT" "0" "$CURRENT_TEST"
    pass_test "$CURRENT_TEST"
}

test_list_agents_returns_json() {
    CURRENT_TEST="test_list_agents_returns_json"
    capture_cmd poetry run --directory "$REPO" waggle list-agents
    if [[ "$CMD_EXIT" -eq 2 ]]; then
        fail_test "$CURRENT_TEST" "exit code was 2 (usage error)"
    fi
    assert_contains "$CMD_OUT" '"status"' "$CURRENT_TEST"
    pass_test "$CURRENT_TEST"
}

test_spawn_agent_missing_args_json() {
    CURRENT_TEST="test_spawn_agent_missing_args_json"
    capture_cmd poetry run --directory "$REPO" waggle spawn-agent
    assert_eq "$CMD_EXIT" "2" "$CURRENT_TEST"
    assert_contains "$CMD_OUT" '"status"' "$CURRENT_TEST"
    pass_test "$CURRENT_TEST"
}

test_close_session_missing_args_json() {
    CURRENT_TEST="test_close_session_missing_args_json"
    capture_cmd poetry run --directory "$REPO" waggle close-session
    assert_eq "$CMD_EXIT" "2" "$CURRENT_TEST"
    assert_contains "$CMD_OUT" '"status"' "$CURRENT_TEST"
    pass_test "$CURRENT_TEST"
}

# ============================================================================
# Run all tests
# ============================================================================

# Phase 1 tests
run_test test_install_sh_runs
run_test test_mcp_registered
run_test test_module_import
run_test test_venv_script_exists

# CLI tests
run_test test_waggle_help_exits_0
run_test test_waggle_no_subcommand_exits_0
run_test test_waggle_serve_help_exits_0
run_test test_waggle_usage_error_json

# Package manager tests
run_test test_pipx_install
run_test test_uv_install

# Lifecycle subcommand tests
run_test test_list_agents_help
run_test test_spawn_agent_help
run_test test_close_session_help
run_test test_delete_repo_agents_help
run_test test_list_agents_returns_json
run_test test_spawn_agent_missing_args_json
run_test test_close_session_missing_args_json

# ============================================================================
# Summary
# ============================================================================

echo ""
echo "========================================="
echo "  Results: $PASS_COUNT passed, $FAIL_COUNT failed (of $TEST_NUM)"
echo "========================================="

if [[ "$FAIL_COUNT" -gt 0 ]]; then
    exit 1
fi
exit 0
