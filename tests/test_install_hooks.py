"""Unit tests for waggle.installer (t1.fg8.pr).

Tests the waggle install command:
- Missing claude-status exits non-zero with actionable message
- Happy path invokes claude-status install-hooks with correct env and argv
- --auq-order flag is forwarded
- Obsolete hook template file is deleted

No conftest.py.  No real subprocess or filesystem mutations.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import waggle.installer as ins


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _args(auq_order=None):
    return SimpleNamespace(auq_order=auq_order)


def _mock_which(name):
    """Return a fake path for claude-status, None for anything else."""
    return "/usr/local/bin/claude-status" if name == "claude-status" else None


# ---------------------------------------------------------------------------
# Missing claude-status binary
# ---------------------------------------------------------------------------


class TestMissingBinary:
    def test_exits_nonzero_when_binary_absent(self, capsys):
        with patch("shutil.which", return_value=None):
            with pytest.raises(SystemExit) as exc:
                ins.handle_install(_args())
        assert exc.value.code != 0

    def test_error_names_missing_dependency(self, capsys):
        with patch("shutil.which", return_value=None):
            with pytest.raises(SystemExit):
                ins.handle_install(_args())
        err = capsys.readouterr().err
        assert "claude-status" in err

    def test_does_not_invoke_subprocess_when_binary_absent(self):
        with patch("shutil.which", return_value=None):
            with patch("waggle.installer._run_install_hooks") as mock_run:
                with pytest.raises(SystemExit):
                    ins.handle_install(_args())
        mock_run.assert_not_called()


# ---------------------------------------------------------------------------
# Happy path — env vars and argv
# ---------------------------------------------------------------------------


class TestHappyPath:
    def test_exits_0_on_success(self):
        with patch("shutil.which", side_effect=_mock_which):
            with patch("waggle.installer._run_install_hooks", return_value=("OK\n", "", 0)):
                with pytest.raises(SystemExit) as exc:
                    ins.handle_install(_args())
        assert exc.value.code == 0

    def test_relay_mode_in_env(self):
        captured_env = {}

        def capture(argv, env):
            captured_env.update(env)
            return ("", "", 0)

        with patch("shutil.which", side_effect=_mock_which):
            with patch("waggle.installer._run_install_hooks", side_effect=capture):
                with pytest.raises(SystemExit):
                    ins.handle_install(_args())

        assert captured_env.get("CLAUDE_STATUS_RELAY_MODE") == "on"

    def test_auq_mode_in_env(self):
        captured_env = {}

        def capture(argv, env):
            captured_env.update(env)
            return ("", "", 0)

        with patch("shutil.which", side_effect=_mock_which):
            with patch("waggle.installer._run_install_hooks", side_effect=capture):
                with pytest.raises(SystemExit):
                    ins.handle_install(_args())

        assert captured_env.get("CLAUDE_STATUS_AUQ_MODE") == "record"

    def test_env_inherits_os_environ(self):
        captured_env = {}

        def capture(argv, env):
            captured_env.update(env)
            return ("", "", 0)

        with patch.dict(os.environ, {"MY_CUSTOM_VAR": "hello"}):
            with patch("shutil.which", side_effect=_mock_which):
                with patch("waggle.installer._run_install_hooks", side_effect=capture):
                    with pytest.raises(SystemExit):
                        ins.handle_install(_args())

        assert captured_env.get("MY_CUSTOM_VAR") == "hello"

    def test_no_auq_order_means_no_extra_argv(self):
        captured_argv = []

        def capture(argv, env):
            captured_argv.extend(argv)
            return ("", "", 0)

        with patch("shutil.which", side_effect=_mock_which):
            with patch("waggle.installer._run_install_hooks", side_effect=capture):
                with pytest.raises(SystemExit):
                    ins.handle_install(_args())

        assert "--auq-order" not in captured_argv


# ---------------------------------------------------------------------------
# --auq-order forwarding
# ---------------------------------------------------------------------------


class TestAuqOrderForwarding:
    def test_auq_order_forwarded_in_argv(self):
        captured_argv = []

        def capture(argv, env):
            captured_argv.extend(argv)
            return ("", "", 0)

        with patch("shutil.which", side_effect=_mock_which):
            with patch("waggle.installer._run_install_hooks", side_effect=capture):
                with pytest.raises(SystemExit):
                    ins.handle_install(_args(auq_order="last"))

        assert "--auq-order" in captured_argv
        idx = captured_argv.index("--auq-order")
        assert captured_argv[idx + 1] == "last"

    def test_auq_order_before_waggle(self):
        captured_argv = []

        def capture(argv, env):
            captured_argv.extend(argv)
            return ("", "", 0)

        with patch("shutil.which", side_effect=_mock_which):
            with patch("waggle.installer._run_install_hooks", side_effect=capture):
                with pytest.raises(SystemExit):
                    ins.handle_install(_args(auq_order="before:waggle"))

        assert "--auq-order" in captured_argv
        idx = captured_argv.index("--auq-order")
        assert captured_argv[idx + 1] == "before:waggle"


# ---------------------------------------------------------------------------
# Subprocess failure
# ---------------------------------------------------------------------------


class TestSubprocessFailure:
    def test_exits_nonzero_on_nonzero_rc(self):
        with patch("shutil.which", side_effect=_mock_which):
            with patch("waggle.installer._run_install_hooks",
                       return_value=("", "hook error", 1)):
                with pytest.raises(SystemExit) as exc:
                    ins.handle_install(_args())
        assert exc.value.code != 0


# ---------------------------------------------------------------------------
# Legacy hook template deletion
# ---------------------------------------------------------------------------


class TestLegacyTemplateRemoval:
    def test_template_file_deleted_if_present(self, tmp_path, monkeypatch):
        # Create a fake hooks/settings.json.template under tmp_path
        hooks_dir = tmp_path / "hooks"
        hooks_dir.mkdir()
        template = hooks_dir / "settings.json.template"
        template.write_text("{}")

        # Run from tmp_path so the relative Path("hooks/...") resolves correctly.
        monkeypatch.chdir(tmp_path)

        with patch("shutil.which", side_effect=_mock_which):
            with patch("waggle.installer._run_install_hooks", return_value=("", "", 0)):
                with pytest.raises(SystemExit):
                    ins.handle_install(_args())

        assert not template.exists(), "settings.json.template should have been deleted"

    def test_no_error_if_template_absent(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)

        with patch("shutil.which", side_effect=_mock_which):
            with patch("waggle.installer._run_install_hooks", return_value=("", "", 0)):
                with pytest.raises(SystemExit) as exc:
                    ins.handle_install(_args())

        assert exc.value.code == 0
