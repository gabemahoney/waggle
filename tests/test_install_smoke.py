"""Smoke tests for install.sh — uses mocked system commands (no real systemctl/claude)."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def install_env(tmp_path):
    """Set up a fake environment for install.sh testing."""
    home = tmp_path / "home"
    home.mkdir()
    (home / ".claude").mkdir(parents=True)

    # Fake project dir with required files
    project = tmp_path / "project"
    project.mkdir()
    (project / "pyproject.toml").write_text('[tool.poetry]\nname = "waggle"\n')

    # Copy real install.sh
    repo_root = Path(__file__).parent.parent
    real_install = repo_root / "install.sh"
    shutil.copy(real_install, project / "install.sh")

    # Copy waggle.service (install.sh copies this into systemd dir)
    real_service = repo_root / "waggle.service"
    if real_service.exists():
        shutil.copy(real_service, project / "waggle.service")
    else:
        (project / "waggle.service").write_text("[Unit]\nDescription=Waggle\n")

    # Mock binaries — log their args then exit 0
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for cmd in ["poetry", "systemctl", "claude"]:
        log_file = bin_dir / f"{cmd}_calls.txt"
        script = bin_dir / cmd
        script.write_text(
            f'#!/bin/bash\necho "$@" >> "{log_file}"\nexit 0\n'
        )
        script.chmod(0o755)

    return {"home": home, "project": project, "bin_dir": bin_dir}


def _run_install(install_env, args=""):
    env = {
        "HOME": str(install_env["home"]),
        "PATH": f"{install_env['bin_dir']}:/usr/bin:/bin",
    }
    cmd = f"bash {install_env['project']}/install.sh {args}"
    return subprocess.run(cmd, shell=True, env=env, capture_output=True, text=True, timeout=30)


# ---------------------------------------------------------------------------
# Test 1: install.sh exits 0
# ---------------------------------------------------------------------------


def test_install_sh_runs_without_error(install_env):
    result = _run_install(install_env)
    assert result.returncode == 0, (
        f"install.sh failed\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )
    # Verify systemctl was actually invoked (daemon-reload + enable)
    systemctl_log = install_env["bin_dir"] / "systemctl_calls.txt"
    assert systemctl_log.exists(), "systemctl was never called during install"
    calls = systemctl_log.read_text()
    assert "daemon-reload" in calls or "enable" in calls, (
        f"Expected systemctl daemon-reload/enable call, got:\n{calls}"
    )


# ---------------------------------------------------------------------------
# Test 2: install.sh writes waggle hooks into settings.json
# ---------------------------------------------------------------------------


def test_install_sh_deploys_hooks(install_env):
    _run_install(install_env)

    settings_path = install_env["home"] / ".claude" / "settings.json"
    assert settings_path.exists(), "settings.json not created by install.sh"

    with open(settings_path) as f:
        cfg = json.load(f)

    all_commands = [
        h.get("command", "")
        for entries in cfg.get("hooks", {}).values()
        for e in entries
        for h in e.get("hooks", [])
    ]
    waggle_cmds = {"waggle set-state", "waggle permission-request", "waggle ask-relay"}
    assert any(any(wc in c for wc in waggle_cmds) for c in all_commands), (
        f"Waggle hooks not found in settings.json. Commands found: {all_commands}"
    )


# ---------------------------------------------------------------------------
# Test 3: install.sh does NOT use --transport stdio for MCP
# ---------------------------------------------------------------------------


def test_install_sh_no_stdio_mcp():
    install_sh = Path(__file__).parent.parent / "install.sh"
    content = install_sh.read_text()
    assert "--transport stdio" not in content, (
        "install.sh must not register the MCP server with --transport stdio"
    )


# ---------------------------------------------------------------------------
# Test 4: install.sh --uninstall removes service and hooks
# ---------------------------------------------------------------------------


def test_install_sh_uninstall(install_env):
    # Pre-populate settings.json with waggle hooks so the uninstall has something to remove
    waggle_hooks = {
        "hooks": {
            "SessionStart": [{"hooks": [{"type": "command", "command": "waggle set-state waiting"}]}],
            "Stop": [{"hooks": [{"type": "command", "command": "waggle set-state waiting"}]}],
            "UserPromptSubmit": [{"hooks": [{"type": "command", "command": "waggle set-state working"}]}],
        }
    }
    settings_path = install_env["home"] / ".claude" / "settings.json"
    with open(settings_path, "w") as f:
        json.dump(waggle_hooks, f)

    result = _run_install(install_env, "--uninstall")
    assert result.returncode == 0, (
        f"install.sh --uninstall failed\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )

    # Waggle hooks should be gone from settings.json
    with open(settings_path) as f:
        cfg = json.load(f)

    all_commands = [
        h.get("command", "")
        for entries in cfg.get("hooks", {}).values()
        for e in entries
        for h in e.get("hooks", [])
    ]
    waggle_cmds = {"waggle set-state", "waggle permission-request", "waggle ask-relay"}
    assert not any(any(wc in c for wc in waggle_cmds) for c in all_commands), (
        "Waggle hooks should be removed after --uninstall"
    )

    # Verify systemctl was invoked (stop or disable)
    systemctl_log = install_env["bin_dir"] / "systemctl_calls.txt"
    assert systemctl_log.exists(), "systemctl was never called during uninstall"
    calls = systemctl_log.read_text()
    assert any(kw in calls for kw in ("stop", "disable")), (
        f"Expected systemctl stop/disable call, got:\n{calls}"
    )
