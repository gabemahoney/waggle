"""Tests for the waggle package entry point configuration."""

import importlib.metadata
import os
import shutil
import subprocess
import sys

import pytest


class TestEntryPointMetadata:
    def test_entry_point_present_in_metadata(self):
        eps = importlib.metadata.entry_points()
        if hasattr(eps, "select"):
            console_scripts = eps.select(group="console_scripts")
        else:
            console_scripts = eps.get("console_scripts", [])
        names = [ep.name for ep in console_scripts]
        assert "claude-spawn" in names

    def test_entry_point_resolves_to_cli_module(self):
        eps = importlib.metadata.entry_points()
        if hasattr(eps, "select"):
            console_scripts = eps.select(group="console_scripts")
        else:
            console_scripts = eps.get("console_scripts", [])
        claude_spawn_eps = [ep for ep in console_scripts if ep.name == "claude-spawn"]
        assert len(claude_spawn_eps) == 1
        assert claude_spawn_eps[0].value.startswith("claude_spawn.cli:")


class TestEntryPointSubprocess:
    def test_claude_spawn_help_subprocess_exits_0(self):
        claude_spawn_bin = shutil.which("claude-spawn") or os.path.join(
            os.path.dirname(sys.executable), "claude-spawn"
        )
        result = subprocess.run(
            [claude_spawn_bin, "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        assert "ImportError" not in result.stderr
