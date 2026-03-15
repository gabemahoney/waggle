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
        assert "waggle" in names

    def test_entry_point_resolves_to_cli_module(self):
        eps = importlib.metadata.entry_points()
        if hasattr(eps, "select"):
            console_scripts = eps.select(group="console_scripts")
        else:
            console_scripts = eps.get("console_scripts", [])
        waggle_eps = [ep for ep in console_scripts if ep.name == "waggle"]
        assert len(waggle_eps) == 1
        assert waggle_eps[0].value.startswith("waggle.cli:")


class TestEntryPointSubprocess:
    def test_waggle_help_subprocess_exits_0(self):
        waggle_bin = shutil.which("waggle") or os.path.join(
            os.path.dirname(sys.executable), "waggle"
        )
        result = subprocess.run(
            [waggle_bin, "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        assert "ImportError" not in result.stderr
