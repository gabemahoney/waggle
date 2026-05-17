"""Tests for the write-template CLI subcommand (t3.nwq.sn.wj.u6).

Covers Epic 6 AC 1-8:
- AC1: Flag-driven mode (minimal + full options)
- AC2: Interactive mode happy path
- AC3: Interactive mode cancellation (EOFError, KeyboardInterrupt)
- AC4: Mode-conflict rejection (--interactive mutually exclusive with flags)
- AC5: Error pass-through (ErrTemplateOptionsInvalid, ErrTemplateNameUnsafe,
       ErrTemplateExists, force overwrite)
- AC6: Cross-surface equivalence (flag-driven CLI, interactive CLI, MCP)

Pattern: monkeypatch.setattr(sys, "argv", [...]), call cli.main(),
         capture stdout via capsys, parse the JSON line, assert on it.
"""

from __future__ import annotations

import asyncio
import builtins
import json
import os
import sys
import tomllib

import pytest
import tomli_w

from claude_spawn import cli
from claude_spawn.cli import main
from claude_spawn.templates import write_template_impl, load_template
import claude_spawn.mcp_stdio as ms

from tests.helpers import fake_templates_dir
from tests.sample_payloads import TEMPLATE_TOML_FULL, TEMPLATE_TOML_MINIMAL

# Parse the canonical full-options fixture once (no literal TOML here).
_FULL_OPTIONS = tomllib.loads(TEMPLATE_TOML_FULL)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_stdout_json(captured_out: str) -> dict:
    """Extract the first non-empty JSON line from captured stdout."""
    for line in captured_out.splitlines():
        line = line.strip()
        if line.startswith("{"):
            return json.loads(line)
    raise AssertionError(f"No JSON line found in stdout:\n{captured_out!r}")


def _make_input_side_effect(*responses: str):
    """Return a builtins.input side-effect that yields responses then falls back to ''.

    Each call to input() (regardless of the prompt string) consumes the next
    response.  When the list is exhausted, the side-effect returns '' to
    terminate any sub-loops that read until a blank/skip token.
    """
    it = iter(responses)

    def _input(prompt: str = "") -> str:
        try:
            return next(it)
        except StopIteration:
            return ""

    return _input


# ---------------------------------------------------------------------------
# TestFlagDrivenMinimal (Epic AC1 — minimal happy path)
# ---------------------------------------------------------------------------


class TestFlagDrivenMinimal:
    """Flag-driven mode with only --cwd=/tmp: exit 0, JSON line, file on disk."""

    def test_exit_0(self, monkeypatch, capsys):
        with fake_templates_dir({}) as tdir:
            monkeypatch.setattr(sys, "argv", ["claude-spawn", "write-template", "orch", "--cwd=/tmp"])
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0

    def test_stdout_is_single_json_line_ok_true(self, monkeypatch, capsys):
        with fake_templates_dir({}):
            monkeypatch.setattr(sys, "argv", ["claude-spawn", "write-template", "orch", "--cwd=/tmp"])
            with pytest.raises(SystemExit):
                main()
            captured = capsys.readouterr()
        result = _parse_stdout_json(captured.out)
        assert result.get("ok") is True, f"expected ok=True, got {result!r}"

    def test_path_ends_with_orch_toml(self, monkeypatch, capsys):
        with fake_templates_dir({}):
            monkeypatch.setattr(sys, "argv", ["claude-spawn", "write-template", "orch", "--cwd=/tmp"])
            with pytest.raises(SystemExit):
                main()
            captured = capsys.readouterr()
        result = _parse_stdout_json(captured.out)
        assert result["path"].endswith("/orch.toml"), (
            f"expected path ending in /orch.toml, got {result['path']!r}"
        )

    def test_options_match_cwd_flag(self, monkeypatch, capsys):
        with fake_templates_dir({}):
            monkeypatch.setattr(sys, "argv", ["claude-spawn", "write-template", "orch", "--cwd=/tmp"])
            with pytest.raises(SystemExit):
                main()
            captured = capsys.readouterr()
        result = _parse_stdout_json(captured.out)
        assert result["options"] == {"cwd": "/tmp"}, (
            f"expected options={{'cwd': '/tmp'}}, got {result['options']!r}"
        )

    def test_file_on_disk_matches_direct_impl(self, monkeypatch, capsys):
        """File produced by CLI must be byte-identical to a direct write_template_impl call."""
        with fake_templates_dir({}) as tdir:
            # CLI call
            monkeypatch.setattr(sys, "argv", ["claude-spawn", "write-template", "orch", "--cwd=/tmp"])
            with pytest.raises(SystemExit):
                main()
            cli_path = os.path.join(tdir, "orch.toml")
            cli_bytes = open(cli_path, "rb").read()

            # Direct impl call to a second name
            impl_result = write_template_impl("orch_direct", {"cwd": "/tmp"}, force=False)
            assert impl_result["ok"] is True
            impl_bytes = open(impl_result["path"], "rb").read()

        assert cli_bytes == impl_bytes, (
            "CLI-produced TOML differs from direct write_template_impl output"
        )

    def test_file_loadable_via_loader(self, monkeypatch, capsys):
        with fake_templates_dir({}):
            monkeypatch.setattr(sys, "argv", ["claude-spawn", "write-template", "orch", "--cwd=/tmp"])
            with pytest.raises(SystemExit):
                main()
            loaded = load_template("orch")
        assert loaded["ok"] is True
        assert loaded["load_template"] == {"cwd": "/tmp"}


# ---------------------------------------------------------------------------
# TestFlagDrivenFull (all options including repeatables)
# ---------------------------------------------------------------------------


class TestFlagDrivenFull:
    """Flag-driven mode with every option flag: verify loaded options match intent."""

    _ARGV = [
        "claude-spawn", "write-template", "full",
        "--cwd=/work/repo",
        "--model=claude-opus-4-5",
        "--thinking=high",
        "--tmux-session-name=orch-main",
        "--instance-id=test-instance-001",
        "--claude-home=/custom/home",
        "--claude-settings=/path/to/settings.json",
        "--claude-arg=--dangerously-skip-permissions",
        "--claude-arg=--verbose",
        "--extra-env-entry=FOO=bar",
        "--extra-env-entry=BAZ=qux",
        "--claude-status-labels-entry=role=orchestrator",
        "--claude-status-labels-entry=project=waggle",
        "--permissions-allow=Bash",
        "--permissions-allow=Read",
        "--permissions-deny=WebFetch",
        "--permissions-ask=Write",
    ]

    def test_exit_0(self, monkeypatch, capsys):
        with fake_templates_dir({}):
            monkeypatch.setattr(sys, "argv", self._ARGV)
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0

    def test_loaded_options_match_full_fixture(self, monkeypatch, capsys):
        """Loaded options map must equal _FULL_OPTIONS (parsed from TEMPLATE_TOML_FULL)."""
        with fake_templates_dir({}):
            monkeypatch.setattr(sys, "argv", self._ARGV)
            with pytest.raises(SystemExit):
                main()
            loaded = load_template("full")
        assert loaded["ok"] is True, f"load failed: {loaded!r}"
        assert loaded["load_template"] == _FULL_OPTIONS, (
            f"loaded options differ from _FULL_OPTIONS:\n"
            f"  got:      {loaded['load_template']!r}\n"
            f"  expected: {_FULL_OPTIONS!r}"
        )

    def test_stdout_ok_true(self, monkeypatch, capsys):
        with fake_templates_dir({}):
            monkeypatch.setattr(sys, "argv", self._ARGV)
            with pytest.raises(SystemExit):
                main()
            captured = capsys.readouterr()
        result = _parse_stdout_json(captured.out)
        assert result.get("ok") is True


# ---------------------------------------------------------------------------
# TestInteractiveHappyPath (Epic AC2)
# ---------------------------------------------------------------------------


class TestInteractiveHappyPath:
    """Interactive mode driven by patched builtins.input → file written, options correct."""

    # Input sequence for a minimal interactive session:
    # The interactive helper iterates options in SR-1.1 order.
    # We respond "/tmp" for the first scalar (cwd), "skip" for all remaining
    # scalars, and "" (blank) to terminate each sub-collection loop.
    # If the implementation uses a different first prompt, adjust accordingly.
    _INPUT_RESPONSES = (
        "/tmp",    # cwd
        "skip",    # model
        "skip",    # thinking
        "skip",    # tmux_session_name
        "skip",    # instance_id
        "skip",    # claude_home
        "skip",    # claude_settings
        "",        # terminate claude_args sub-loop
        "",        # terminate extra_env sub-loop
        "",        # terminate claude_status_labels sub-loop
        "",        # terminate permissions.allow sub-loop
        "",        # terminate permissions.deny sub-loop
        "",        # terminate permissions.ask sub-loop
    )

    def test_exit_0(self, monkeypatch, capsys):
        with fake_templates_dir({}):
            monkeypatch.setattr(sys, "argv", ["claude-spawn", "write-template", "orch2", "--interactive"])
            monkeypatch.setattr(builtins, "input", _make_input_side_effect(*self._INPUT_RESPONSES))
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0

    def test_file_written(self, monkeypatch, capsys):
        with fake_templates_dir({}) as tdir:
            monkeypatch.setattr(sys, "argv", ["claude-spawn", "write-template", "orch2", "--interactive"])
            monkeypatch.setattr(builtins, "input", _make_input_side_effect(*self._INPUT_RESPONSES))
            with pytest.raises(SystemExit):
                main()
            assert os.path.exists(os.path.join(tdir, "orch2.toml")), (
                "expected orch2.toml to exist after interactive write"
            )

    def test_options_match_flag_driven_equivalent(self, monkeypatch, capsys):
        """Interactive result must equal what a flag-driven call with same inputs produces."""
        with fake_templates_dir({}) as tdir:
            # Interactive call
            monkeypatch.setattr(sys, "argv", ["claude-spawn", "write-template", "orch2", "--interactive"])
            monkeypatch.setattr(builtins, "input", _make_input_side_effect(*self._INPUT_RESPONSES))
            with pytest.raises(SystemExit):
                main()
            interactive_loaded = load_template("orch2")

            # Flag-driven call producing the same effective options
            monkeypatch.setattr(sys, "argv", ["claude-spawn", "write-template", "orch2_flag", "--cwd=/tmp"])
            with pytest.raises(SystemExit):
                main()
            flag_loaded = load_template("orch2_flag")

        assert interactive_loaded["ok"] is True, f"interactive load failed: {interactive_loaded!r}"
        assert flag_loaded["ok"] is True, f"flag load failed: {flag_loaded!r}"
        assert interactive_loaded["load_template"] == flag_loaded["load_template"], (
            f"interactive options {interactive_loaded['load_template']!r} != "
            f"flag-driven options {flag_loaded['load_template']!r}"
        )


# ---------------------------------------------------------------------------
# TestInteractiveCancellation (Epic AC3)
# ---------------------------------------------------------------------------


class TestInteractiveCancellation:
    """Cancellation via EOFError or KeyboardInterrupt → error JSON + non-zero exit + no file."""

    def test_eoferror_after_first_prompt_emits_error_json(self, monkeypatch, capsys):
        calls = [0]

        def _input_raises(prompt: str = "") -> str:
            calls[0] += 1
            if calls[0] >= 2:
                raise EOFError
            return "orch3_name_unused"

        with fake_templates_dir({}) as tdir:
            monkeypatch.setattr(sys, "argv", ["claude-spawn", "write-template", "orch3", "--interactive"])
            monkeypatch.setattr(builtins, "input", _input_raises)
            with pytest.raises(SystemExit) as exc_info:
                main()
            captured = capsys.readouterr()
            files = os.listdir(tdir)

        result = _parse_stdout_json(captured.out)
        assert result.get("status") == "error", f"expected status=error, got {result!r}"
        assert result.get("message") == "write-template cancelled", (
            f"expected message='write-template cancelled', got {result!r}"
        )
        assert exc_info.value.code != 0, f"expected non-zero exit, got {exc_info.value.code}"
        assert files == [], f"expected no files written on cancellation, found {files}"

    def test_eoferror_exit_code_nonzero(self, monkeypatch, capsys):
        def _raises(_prompt: str = "") -> str:
            raise EOFError

        with fake_templates_dir({}):
            monkeypatch.setattr(sys, "argv", ["claude-spawn", "write-template", "orch3", "--interactive"])
            monkeypatch.setattr(builtins, "input", _raises)
            with pytest.raises(SystemExit) as exc_info:
                main()
        assert exc_info.value.code != 0

    def test_keyboard_interrupt_emits_error_json(self, monkeypatch, capsys):
        calls = [0]

        def _input_raises(prompt: str = "") -> str:
            calls[0] += 1
            if calls[0] >= 2:
                raise KeyboardInterrupt
            return "unused"

        with fake_templates_dir({}) as tdir:
            monkeypatch.setattr(sys, "argv", ["claude-spawn", "write-template", "orch4", "--interactive"])
            monkeypatch.setattr(builtins, "input", _input_raises)
            with pytest.raises(SystemExit) as exc_info:
                main()
            captured = capsys.readouterr()
            files = os.listdir(tdir)

        result = _parse_stdout_json(captured.out)
        assert result.get("status") == "error", f"expected status=error, got {result!r}"
        assert result.get("message") == "write-template cancelled", (
            f"expected cancellation message, got {result!r}"
        )
        assert exc_info.value.code != 0
        assert files == [], f"expected no files on interrupt cancellation, found {files}"

    def test_keyboard_interrupt_no_file_written(self, monkeypatch, capsys):
        def _raises(_prompt: str = "") -> str:
            raise KeyboardInterrupt

        with fake_templates_dir({}) as tdir:
            monkeypatch.setattr(sys, "argv", ["claude-spawn", "write-template", "orch4", "--interactive"])
            monkeypatch.setattr(builtins, "input", _raises)
            with pytest.raises(SystemExit):
                main()
            files = os.listdir(tdir)
        assert files == [], f"expected no files, found {files}"


# ---------------------------------------------------------------------------
# TestModeConflict (Epic AC4)
# ---------------------------------------------------------------------------


class TestModeConflict:
    """--interactive is mutually exclusive with option flags → error exit, nothing written."""

    def test_interactive_plus_cwd_exits_nonzero(self, monkeypatch, capsys):
        with fake_templates_dir({}):
            monkeypatch.setattr(
                sys, "argv",
                ["claude-spawn", "write-template", "foo", "--interactive", "--cwd=/tmp"]
            )
            with pytest.raises(SystemExit) as exc_info:
                main()
        assert exc_info.value.code != 0, (
            f"expected non-zero exit for mode conflict, got {exc_info.value.code}"
        )

    def test_interactive_plus_cwd_emits_error_json(self, monkeypatch, capsys):
        with fake_templates_dir({}):
            monkeypatch.setattr(
                sys, "argv",
                ["claude-spawn", "write-template", "foo", "--interactive", "--cwd=/tmp"]
            )
            with pytest.raises(SystemExit):
                main()
            captured = capsys.readouterr()
        # Either argparse-level {"status":"error","message":...} or app-level {"ok":False,...}
        result = _parse_stdout_json(captured.out)
        has_error = (
            result.get("status") == "error"
            or result.get("ok") is False
        )
        assert has_error, f"expected an error envelope, got {result!r}"

    def test_interactive_plus_cwd_no_file_written(self, monkeypatch, capsys):
        with fake_templates_dir({}) as tdir:
            monkeypatch.setattr(
                sys, "argv",
                ["claude-spawn", "write-template", "foo", "--interactive", "--cwd=/tmp"]
            )
            with pytest.raises(SystemExit):
                main()
            files = [f for f in os.listdir(tdir) if f.endswith(".toml")]
        assert files == [], f"expected no file written for mode conflict, found {files}"

    def test_interactive_plus_model_exits_nonzero(self, monkeypatch, capsys):
        """Any option flag + --interactive must be rejected."""
        with fake_templates_dir({}):
            monkeypatch.setattr(
                sys, "argv",
                ["claude-spawn", "write-template", "bar", "--interactive", "--model=claude-opus-4-5"]
            )
            with pytest.raises(SystemExit) as exc_info:
                main()
        assert exc_info.value.code != 0


# ---------------------------------------------------------------------------
# TestErrorPassThrough (Epic AC5)
# ---------------------------------------------------------------------------


class TestErrorPassThrough:
    """Each impl error is surfaced correctly: stdout JSON has err_name, exit code non-zero."""

    def _run(self, monkeypatch, capsys, argv):
        """Run with given argv inside fake_templates_dir({}); return (result_dict, exit_code, files)."""
        with fake_templates_dir({}) as tdir:
            monkeypatch.setattr(sys, "argv", argv)
            with pytest.raises(SystemExit) as exc_info:
                main()
            captured = capsys.readouterr()
            files = [f for f in os.listdir(tdir) if not f.endswith(".toml.tmp")]
        return _parse_stdout_json(captured.out), exc_info.value.code, files

    def test_invalid_thinking_value_err_template_options_invalid(self, monkeypatch, capsys):
        result, code, files = self._run(
            monkeypatch, capsys,
            ["claude-spawn", "write-template", "bad_think", "--thinking=huge", "--cwd=/tmp"]
        )
        assert result.get("err_name") == "ErrTemplateOptionsInvalid", (
            f"expected ErrTemplateOptionsInvalid, got {result!r}"
        )
        assert code != 0, f"expected non-zero exit, got {code}"
        toml_files = [f for f in files if f.endswith(".toml")]
        assert toml_files == [], f"expected no file written, found {toml_files}"

    def test_unsafe_name_err_template_name_unsafe(self, monkeypatch, capsys):
        result, code, files = self._run(
            monkeypatch, capsys,
            ["claude-spawn", "write-template", "foo/bar", "--cwd=/tmp"]
        )
        assert result.get("err_name") == "ErrTemplateNameUnsafe", (
            f"expected ErrTemplateNameUnsafe, got {result!r}"
        )
        assert code != 0

    def test_collision_without_force_err_template_exists(self, monkeypatch, capsys):
        with fake_templates_dir({}) as tdir:
            # First call — must succeed
            monkeypatch.setattr(sys, "argv", ["claude-spawn", "write-template", "dup", "--cwd=/tmp/v1"])
            with pytest.raises(SystemExit) as exc1:
                main()
            assert exc1.value.code == 0, "first write must succeed"
            _ = capsys.readouterr()  # clear

            # Second call — same name, no --force
            monkeypatch.setattr(sys, "argv", ["claude-spawn", "write-template", "dup", "--cwd=/tmp/v2"])
            with pytest.raises(SystemExit) as exc2:
                main()
            captured2 = capsys.readouterr()

        result2 = _parse_stdout_json(captured2.out)
        assert result2.get("err_name") == "ErrTemplateExists", (
            f"expected ErrTemplateExists, got {result2!r}"
        )
        assert exc2.value.code != 0

    def test_collision_with_force_succeeds_and_overwrites(self, monkeypatch, capsys):
        with fake_templates_dir({}) as tdir:
            # First call
            monkeypatch.setattr(sys, "argv", ["claude-spawn", "write-template", "dup", "--cwd=/tmp/v1"])
            with pytest.raises(SystemExit) as exc1:
                main()
            assert exc1.value.code == 0
            _ = capsys.readouterr()

            # Second call with --force
            monkeypatch.setattr(
                sys, "argv",
                ["claude-spawn", "write-template", "dup", "--cwd=/tmp/v2", "--force"]
            )
            with pytest.raises(SystemExit) as exc2:
                main()
            captured2 = capsys.readouterr()
            loaded = load_template("dup")

        result2 = _parse_stdout_json(captured2.out)
        assert result2.get("ok") is True, f"force overwrite should succeed, got {result2!r}"
        assert exc2.value.code == 0
        assert loaded["ok"] is True
        assert loaded["load_template"].get("cwd") == "/tmp/v2", (
            f"expected cwd=/tmp/v2 after force overwrite, got {loaded['load_template']!r}"
        )

    def test_invalid_thinking_exit_code_nonzero(self, monkeypatch, capsys):
        result, code, _ = self._run(
            monkeypatch, capsys,
            ["claude-spawn", "write-template", "bad_think2", "--thinking=huge", "--cwd=/tmp"]
        )
        assert code != 0


# ---------------------------------------------------------------------------
# TestSurfacesConverge (Epic AC6)
# ---------------------------------------------------------------------------


class TestSurfacesConverge:
    """Flag-driven CLI, interactive CLI, and MCP tool all produce identical option maps."""

    # Simple bundle easy to author on all three surfaces.
    _BUNDLE = {"cwd": "/tmp/convergence"}
    _BUNDLE_ARGV_FLAGS = ["--cwd=/tmp/convergence"]

    # Interactive input sequence for _BUNDLE (cwd first, everything else skipped/blank).
    _INTERACTIVE_RESPONSES = (
        "/tmp/convergence",  # cwd
        "skip",              # model
        "skip",              # thinking
        "skip",              # tmux_session_name
        "skip",              # instance_id
        "skip",              # claude_home
        "skip",              # claude_settings
        "",                  # terminate claude_args
        "",                  # terminate extra_env
        "",                  # terminate claude_status_labels
        "",                  # terminate permissions.allow
        "",                  # terminate permissions.deny
        "",                  # terminate permissions.ask
    )

    def test_all_three_surfaces_produce_identical_option_maps(self, monkeypatch, capsys):
        """(a) flag-driven CLI, (b) interactive CLI, (c) MCP — same loaded options."""
        with fake_templates_dir({}) as tdir:
            # (a) Flag-driven CLI
            monkeypatch.setattr(
                sys, "argv",
                ["claude-spawn", "write-template", "conv_flag"] + self._BUNDLE_ARGV_FLAGS
            )
            with pytest.raises(SystemExit) as exc_a:
                main()
            assert exc_a.value.code == 0, "flag-driven call must succeed"
            _ = capsys.readouterr()

            # (b) Interactive CLI
            monkeypatch.setattr(
                sys, "argv",
                ["claude-spawn", "write-template", "conv_interactive", "--interactive"]
            )
            monkeypatch.setattr(
                builtins, "input",
                _make_input_side_effect(*self._INTERACTIVE_RESPONSES)
            )
            with pytest.raises(SystemExit) as exc_b:
                main()
            assert exc_b.value.code == 0, "interactive call must succeed"
            _ = capsys.readouterr()

            # (c) MCP tool (direct async call)
            mcp_result = asyncio.get_event_loop().run_until_complete(
                ms.write_template.fn(
                    name="conv_mcp",
                    options=self._BUNDLE,
                    force=False,
                )
            )
            assert mcp_result.get("ok") is not False, f"MCP call failed: {mcp_result!r}"

            # Load all three via the Epic-3 loader and compare
            loaded_a = load_template("conv_flag")
            loaded_b = load_template("conv_interactive")
            loaded_c = load_template("conv_mcp")

        assert loaded_a["ok"] is True, f"flag load failed: {loaded_a!r}"
        assert loaded_b["ok"] is True, f"interactive load failed: {loaded_b!r}"
        assert loaded_c["ok"] is True, f"MCP load failed: {loaded_c!r}"

        opts_a = loaded_a["load_template"]
        opts_b = loaded_b["load_template"]
        opts_c = loaded_c["load_template"]

        assert opts_a == opts_b, (
            f"flag-driven options {opts_a!r} != interactive options {opts_b!r}"
        )
        assert opts_a == opts_c, (
            f"flag-driven options {opts_a!r} != MCP options {opts_c!r}"
        )

    def test_hand_edited_toml_matches_flag_driven(self, monkeypatch, capsys):
        """(d) Hand-edit via tomli_w.dumps produces same options as flag-driven CLI."""
        with fake_templates_dir({}) as tdir:
            # (a) Flag-driven CLI
            monkeypatch.setattr(
                sys, "argv",
                ["claude-spawn", "write-template", "conv_flag2"] + self._BUNDLE_ARGV_FLAGS
            )
            with pytest.raises(SystemExit) as exc_a:
                main()
            assert exc_a.value.code == 0
            _ = capsys.readouterr()

            # (d) Hand-edit: write TOML directly using tomli_w
            hand_path = os.path.join(tdir, "conv_hand.toml")
            with open(hand_path, "wb") as fh:
                fh.write(tomli_w.dumps(self._BUNDLE).encode())

            loaded_a = load_template("conv_flag2")
            loaded_d = load_template("conv_hand")

        assert loaded_a["ok"] is True
        assert loaded_d["ok"] is True
        assert loaded_a["load_template"] == loaded_d["load_template"], (
            f"flag-driven {loaded_a['load_template']!r} != hand-edit {loaded_d['load_template']!r}"
        )
