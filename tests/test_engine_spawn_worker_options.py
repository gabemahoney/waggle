"""Tests for new spawn_worker_impl options surface.

Covers:
- SR-3.3: sanitize-folder-name helper table
- SR-3.4: default tmux_session_name composition
- SR-4.1–4.4: launch composition (env vars, start-dir, command-line)
- SR-4.5: settings overlay synthesis
- SR-9.1: validation errors (8 in-scope error names)

No conftest.py.  No real tmux or claude-status subprocess is forked.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from unittest.mock import patch

import pytest

import claude_spawn.spawn as sp
from tests.helpers import (
    fake_claude_status,
    fake_worker_record,
    fake_workers_response,
)

# ---------------------------------------------------------------------------
# Shared test helpers
# ---------------------------------------------------------------------------

_OK_TRIPLE = ("", "", 0)


def _empty_workers_triple() -> tuple[str, str, int]:
    """Canned claude-status triple: success with an empty workers list."""
    payload = json.dumps({"workers": [], "skipped": []})
    return (payload, "", 0)


def _workers_triple_with(records: list[dict]) -> tuple[str, str, int]:
    """Canned claude-status triple: success with a non-empty workers list."""
    payload = json.dumps(fake_workers_response(records))
    return (payload, "", 0)


def _patch_tmux(triples: list[tuple[str, str, int]]):
    """Patch claude_spawn.spawn._tmux and capture calls.

    Returns (calls_list, patcher).  Call patcher.stop() in a finally block.
    If _tmux is called more times than triples are provided the side_effect
    raises AssertionError.
    """
    queue = list(triples)
    calls: list[list[str]] = []

    def side_effect(argv: list[str]) -> tuple[str, str, int]:
        calls.append(list(argv))
        if not queue:
            raise AssertionError(f"_tmux called more times than expected; argv={argv!r}")
        return queue.pop(0)

    patcher = patch("claude_spawn.spawn._tmux", side_effect=side_effect)
    patcher.start()
    return calls, patcher


def _env_pairs(argv: list[str]) -> dict[str, str]:
    """Extract {KEY: VALUE} from -e KEY=VALUE pairs in argv."""
    pairs: dict[str, str] = {}
    i = 0
    while i < len(argv):
        if argv[i] == "-e" and i + 1 < len(argv):
            key, _, val = argv[i + 1].partition("=")
            pairs[key] = val
            i += 2
        else:
            i += 1
    return pairs


def _extract_settings_path(send_keys_argv: list[str]) -> str | None:
    """Extract the --settings path from a send-keys argv list, or None if absent."""
    cmd = " ".join(send_keys_argv)
    m = re.search(r"--settings(?:=|\s+)(\S+)", cmd)
    return m.group(1) if m else None


# ---------------------------------------------------------------------------
# TestSanitizeFolderName — SR-3.3 table
# ---------------------------------------------------------------------------


class TestSanitizeFolderName:
    """One assertion per SR-3.3 example row."""

    def test_long_path_returns_final_segment(self):
        result = sp._sanitize_folder_name(
            "/home/horde/projects/waggle-project/waggle-main"
        )
        assert result == "waggle-main"

    def test_trailing_slash_ignored(self):
        result = sp._sanitize_folder_name(
            "/home/horde/projects/waggle-project/waggle-main/"
        )
        assert result == "waggle-main"

    def test_dots_in_filename_become_dashes(self):
        assert sp._sanitize_folder_name("/path/foo.bar.tar.gz") == "foo-bar-tar-gz"

    def test_colon_becomes_dash(self):
        assert sp._sanitize_folder_name("/path/with:colon") == "with-colon"

    def test_root_path_returns_root(self):
        assert sp._sanitize_folder_name("/") == "root"

    def test_dot_path_returns_root(self):
        assert sp._sanitize_folder_name(".") == "root"


# ---------------------------------------------------------------------------
# TestDefaultTmuxSessionName — SR-3.4
# ---------------------------------------------------------------------------


class TestDefaultTmuxSessionName:
    """Default tmux_session_name is <sanitize(cwd)>-<instance_id[:8]>."""

    def test_default_session_name_composition(self):
        """tmux_session_name == sanitize(cwd) + "-" + instance_id[:8]."""
        fixed_iid = "abcd1234-0000-0000-0000-000000000000"
        cwd = "/tmp"
        calls, patcher = _patch_tmux([_OK_TRIPLE, _OK_TRIPLE])
        try:
            with fake_claude_status([_empty_workers_triple()]):
                result = sp.spawn_worker_impl(cwd=cwd, instance_id=fixed_iid)
        finally:
            patcher.stop()
        expected = f"{sp._sanitize_folder_name(cwd)}-{fixed_iid[:8]}"
        assert result.get("tmux_session_name") == expected

    def test_short_instance_id_no_padding(self):
        """SR-3.4: instance_id shorter than 8 chars — full string is the suffix."""
        short_iid = "abc"
        cwd = "/tmp"
        calls, patcher = _patch_tmux([_OK_TRIPLE, _OK_TRIPLE])
        try:
            with fake_claude_status([_empty_workers_triple()]):
                result = sp.spawn_worker_impl(cwd=cwd, instance_id=short_iid)
        finally:
            patcher.stop()
        expected = f"{sp._sanitize_folder_name(cwd)}-{short_iid}"
        assert result.get("tmux_session_name") == expected


# ---------------------------------------------------------------------------
# TestLaunchComposition — SR-4.1–4.4
# ---------------------------------------------------------------------------


class TestLaunchComposition:
    """tmux new-session and send-keys composition for every option category."""

    def _run(self, **kwargs) -> tuple[list[list[str]], dict]:
        """Call spawn_worker_impl with patched seams; return (tmux_calls, result)."""
        calls, patcher = _patch_tmux([_OK_TRIPLE, _OK_TRIPLE])
        try:
            result = sp.spawn_worker_impl(**kwargs)
        finally:
            patcher.stop()
        return calls, result

    def _run_with_supplied_id(self, instance_id: str = "testid12-0000-0000-0000-000000000000", **kwargs):
        """Like _run, but supply instance_id so collision check fires once."""
        calls, patcher = _patch_tmux([_OK_TRIPLE, _OK_TRIPLE])
        try:
            with fake_claude_status([_empty_workers_triple()]):
                result = sp.spawn_worker_impl(instance_id=instance_id, **kwargs)
        finally:
            patcher.stop()
        return calls, result

    # -- Unconditional env set (SR-4.2) ------------------------------------

    def test_unconditional_env_vars_present(self):
        """All SR-4.2 unconditional env vars are in new-session argv."""
        calls, result = self._run(cwd="/tmp")
        pairs = _env_pairs(calls[0])
        assert "CLAUDE_STATUS_INSTANCE_ID" in pairs
        assert pairs["CLAUDE_STATUS_RELAY_MODE"] == "on"
        assert pairs["CLAUDE_STATUS_AUQ_MODE"] == "record"
        assert pairs["CLAUDE_STATUS_LABEL_CLAUDE_SPAWN_OWNED"] == "1"
        assert "CLAUDE_STATUS_LABEL_CLAUDE_SPAWN_SESSION_NAME" in pairs
        assert pairs["CLAUDE_STATUS_LABEL_CLAUDE_SPAWN_CWD"] == "/tmp"

    def test_required_env_vars_tuple_matches_unconditional_set(self):
        """_REQUIRED_ENV_VARS contains exactly the SR-4.2 unconditional vars."""
        required = set(sp._REQUIRED_ENV_VARS)
        # These six must be present (MODEL is conditional so NOT in the tuple)
        expected = {
            "CLAUDE_STATUS_INSTANCE_ID",
            "CLAUDE_STATUS_RELAY_MODE",
            "CLAUDE_STATUS_AUQ_MODE",
            "CLAUDE_STATUS_LABEL_CLAUDE_SPAWN_OWNED",
            "CLAUDE_STATUS_LABEL_CLAUDE_SPAWN_SESSION_NAME",
            "CLAUDE_STATUS_LABEL_CLAUDE_SPAWN_CWD",
        }
        assert expected <= required, f"missing from _REQUIRED_ENV_VARS: {expected - required}"
        assert "CLAUDE_STATUS_LABEL_CLAUDE_SPAWN_MODEL" not in required, (
            "MODEL label is conditional and must NOT be in _REQUIRED_ENV_VARS"
        )

    # -- Conditional MODEL label (SR-4.2) ----------------------------------

    def test_model_label_present_when_model_supplied(self):
        calls, result = self._run(cwd="/tmp", model="opus")
        pairs = _env_pairs(calls[0])
        assert pairs.get("CLAUDE_STATUS_LABEL_CLAUDE_SPAWN_MODEL") == "opus"

    def test_model_label_absent_when_model_omitted(self):
        calls, result = self._run(cwd="/tmp")
        pairs = _env_pairs(calls[0])
        assert "CLAUDE_STATUS_LABEL_CLAUDE_SPAWN_MODEL" not in pairs

    def test_model_label_value_is_lowercased(self):
        calls, result = self._run(cwd="/tmp", model="Claude-Opus-4-5")
        pairs = _env_pairs(calls[0])
        assert pairs.get("CLAUDE_STATUS_LABEL_CLAUDE_SPAWN_MODEL") == "claude-opus-4-5"

    # -- Start directory (SR-4.1) ------------------------------------------

    def test_new_session_carries_start_directory_flag(self):
        calls, result = self._run(cwd="/tmp")
        new_session_argv = calls[0]
        assert "-c" in new_session_argv
        idx = new_session_argv.index("-c")
        assert new_session_argv[idx + 1] == "/tmp"

    def test_send_keys_does_not_contain_cd_preamble(self):
        calls, result = self._run(cwd="/tmp")
        cmd = " ".join(calls[1])
        assert "cd " not in cmd

    # -- extra_env flow-through (SR-4.3) -----------------------------------

    def test_extra_env_appears_in_new_session(self):
        calls, result = self._run(cwd="/tmp", extra_env={"FOO": "bar", "BAZ": "qux"})
        pairs = _env_pairs(calls[0])
        assert pairs.get("FOO") == "bar"
        assert pairs.get("BAZ") == "qux"

    # -- claude_status_labels uppercased (SR-4.3) --------------------------

    def test_claude_status_labels_uppercased_in_env(self):
        calls, result = self._run(cwd="/tmp", claude_status_labels={"role": "orch"})
        pairs = _env_pairs(calls[0])
        assert pairs.get("CLAUDE_STATUS_LABEL_ROLE") == "orch"

    def test_claude_status_labels_key_upcasing_is_applied(self):
        calls, result = self._run(cwd="/tmp", claude_status_labels={"my_label": "val"})
        pairs = _env_pairs(calls[0])
        assert pairs.get("CLAUDE_STATUS_LABEL_MY_LABEL") == "val"

    # -- claude_home (SR-4.3) ----------------------------------------------

    def test_claude_home_emits_home_env_var(self):
        calls, result = self._run(cwd="/tmp", claude_home="/custom/home")
        pairs = _env_pairs(calls[0])
        assert pairs.get("HOME") == "/custom/home"

    def test_claude_home_absent_when_not_supplied(self):
        calls, result = self._run(cwd="/tmp")
        pairs = _env_pairs(calls[0])
        assert "HOME" not in pairs

    # -- Conditional --model flag (SR-4.4) ---------------------------------

    def test_model_flag_present_in_send_keys_when_model_supplied(self):
        calls, result = self._run(cwd="/tmp", model="opus")
        cmd = " ".join(calls[1])
        assert "--model opus" in cmd

    def test_model_flag_absent_from_send_keys_when_model_omitted(self):
        calls, result = self._run(cwd="/tmp")
        cmd = " ".join(calls[1])
        assert "--model" not in cmd

    # -- Conditional --effort flag (SR-4.4) --------------------------------

    def test_effort_flag_present_when_thinking_supplied(self):
        calls, result = self._run(cwd="/tmp", thinking="xhigh")
        cmd = " ".join(calls[1])
        assert "--effort xhigh" in cmd

    def test_effort_flag_absent_when_thinking_omitted(self):
        calls, result = self._run(cwd="/tmp")
        cmd = " ".join(calls[1])
        assert "--effort" not in cmd

    # -- claude_args verbatim (SR-4.4) ------------------------------------

    def test_claude_args_appended_verbatim(self):
        calls, result = self._run(cwd="/tmp", claude_args=["--dangerously-skip-permissions"])
        cmd = " ".join(calls[1])
        assert "--dangerously-skip-permissions" in cmd

    def test_claude_args_multiple_entries_in_order(self):
        calls, result = self._run(cwd="/tmp", claude_args=["--arg-one", "--arg-two"])
        cmd = " ".join(calls[1])
        idx1 = cmd.find("--arg-one")
        idx2 = cmd.find("--arg-two")
        assert idx1 != -1 and idx2 != -1
        assert idx1 < idx2, "--arg-one must appear before --arg-two"

    # -- Explicit tmux_session_name override (SR-1.1) ----------------------

    def test_explicit_tmux_session_name_used_for_dash_s(self):
        calls, result = self._run(cwd="/tmp", tmux_session_name="my-explicit-sess")
        new_session_argv = calls[0]
        assert "-s" in new_session_argv
        idx = new_session_argv.index("-s")
        assert new_session_argv[idx + 1] == "my-explicit-sess"

    def test_explicit_tmux_session_name_used_as_send_keys_target(self):
        calls, result = self._run(cwd="/tmp", tmux_session_name="my-explicit-sess")
        send_keys_argv = calls[1]
        assert "-t" in send_keys_argv
        idx = send_keys_argv.index("-t")
        assert send_keys_argv[idx + 1] == "my-explicit-sess:0.0"

    # -- Full-option smoke test -------------------------------------------

    def test_full_option_invocation(self):
        """A single invocation with every option exercised."""
        calls, patcher = _patch_tmux([_OK_TRIPLE, _OK_TRIPLE])
        try:
            with fake_claude_status([_empty_workers_triple()]):
                result = sp.spawn_worker_impl(
                    cwd="/tmp",
                    model="opus",
                    thinking="xhigh",
                    extra_env={"FOO": "bar"},
                    claude_status_labels={"role": "orch"},
                    tmux_session_name="full-test-sess",
                    instance_id="abc123de-0000-0000-0000-000000000000",
                )
        finally:
            patcher.stop()

        new_sess_argv = calls[0]
        send_keys_argv = calls[1]
        ns_pairs = _env_pairs(new_sess_argv)
        cmd = " ".join(send_keys_argv)

        # Env vars
        assert ns_pairs.get("CLAUDE_STATUS_LABEL_CLAUDE_SPAWN_MODEL") == "opus"
        assert ns_pairs.get("CLAUDE_STATUS_LABEL_ROLE") == "orch"
        assert ns_pairs.get("FOO") == "bar"
        assert ns_pairs.get("CLAUDE_STATUS_LABEL_CLAUDE_SPAWN_CWD") == "/tmp"

        # Start dir
        assert "-c" in new_sess_argv
        assert new_sess_argv[new_sess_argv.index("-c") + 1] == "/tmp"

        # Session name
        assert new_sess_argv[new_sess_argv.index("-s") + 1] == "full-test-sess"

        # Command line
        assert "--model opus" in cmd
        assert "--effort xhigh" in cmd
        assert "Enter" in send_keys_argv

        # Result
        assert result.get("tmux_session_name") == "full-test-sess"
        assert "instance_id" in result


# ---------------------------------------------------------------------------
# TestSettingsOverlay — SR-4.5
# ---------------------------------------------------------------------------


class TestSettingsOverlay:
    """Settings-overlay synthesis: four primary cases."""

    def _run(self, **kwargs) -> tuple[list[list[str]], dict]:
        calls, patcher = _patch_tmux([_OK_TRIPLE, _OK_TRIPLE])
        try:
            result = sp.spawn_worker_impl(**kwargs)
        finally:
            patcher.stop()
        return calls, result

    def test_neither_supplied_no_settings_flag(self):
        """When neither permissions nor claude_settings supplied, no --settings flag."""
        calls, result = self._run(cwd="/tmp")
        assert _extract_settings_path(calls[1]) is None

    def test_permissions_only_creates_settings_file(self):
        """permissions-only: synthesized file contains exact permissions blob."""
        perms = {"allow": ["Bash"], "deny": ["WebFetch"]}
        calls, result = self._run(cwd="/tmp", permissions=perms)
        path = _extract_settings_path(calls[1])
        assert path is not None, "--settings flag must be present"
        with open(path) as f:
            content = json.load(f)
        assert content == {"permissions": perms}

    def test_permissions_empty_map_no_settings_flag(self):
        """Empty permissions map is treated as 'not supplied' — no --settings."""
        calls, result = self._run(cwd="/tmp", permissions={})
        assert _extract_settings_path(calls[1]) is None

    def test_claude_settings_only_uses_caller_path_verbatim(self):
        """claude_settings-only: --settings points to the caller's file."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            f.write(json.dumps({"theme": "dark"}).encode())
            caller_path = f.name
        try:
            calls, result = self._run(cwd="/tmp", claude_settings=caller_path)
            path = _extract_settings_path(calls[1])
            assert path == caller_path, (
                "--settings must be the caller's file path when no permissions supplied"
            )
        finally:
            os.unlink(caller_path)

    def test_composite_permissions_win_on_allow(self):
        """Composite: per-call permissions.allow overrides file's allow."""
        base = {"permissions": {"allow": ["X"]}, "theme": "dark"}
        with tempfile.NamedTemporaryFile(
            suffix=".json", mode="w", delete=False
        ) as f:
            json.dump(base, f)
            caller_path = f.name
        try:
            calls, result = self._run(
                cwd="/tmp",
                claude_settings=caller_path,
                permissions={"allow": ["Y"]},
            )
            path = _extract_settings_path(calls[1])
            assert path is not None
            assert path != caller_path, "composite must write a new file"
            with open(path) as f:
                content = json.load(f)
            # Per-call allow wins
            assert content["permissions"]["allow"] == ["Y"]
            # Unrelated top-level key passes through unchanged
            assert content.get("theme") == "dark"
        finally:
            os.unlink(caller_path)

    def test_composite_preserves_file_deny_when_per_call_only_has_allow(self):
        """Composite: file deny preserved when per-call supplies allow only."""
        base = {"permissions": {"allow": ["OldAllow"], "deny": ["D"]}}
        with tempfile.NamedTemporaryFile(
            suffix=".json", mode="w", delete=False
        ) as f:
            json.dump(base, f)
            caller_path = f.name
        try:
            calls, result = self._run(
                cwd="/tmp",
                claude_settings=caller_path,
                permissions={"allow": ["A"]},
            )
            path = _extract_settings_path(calls[1])
            assert path is not None
            with open(path) as f:
                content = json.load(f)
            assert content["permissions"]["allow"] == ["A"]
            assert content["permissions"]["deny"] == ["D"]
        finally:
            os.unlink(caller_path)


# ---------------------------------------------------------------------------
# TestValidationErrors — SR-9.1
# ---------------------------------------------------------------------------


class TestValidationErrors:
    """Every in-scope SR-9.1 error name has at least one test.

    Each test asserts:
    - result["err_name"] == expected error name
    - No tmux calls were made (validation aborts before tmux)
    """

    def _assert_error(self, result: dict, calls: list, err_name: str) -> None:
        assert result.get("err_name") == err_name, (
            f"expected err_name={err_name!r}, got {result!r}"
        )
        assert len(calls) == 0, f"expected zero tmux calls, got {len(calls)}: {calls}"

    # -- ErrCwdMissing -----------------------------------------------------

    def test_err_cwd_missing_when_cwd_is_none(self):
        """cwd=None triggers ErrCwdMissing (falsy value check)."""
        calls, patcher = _patch_tmux([])
        try:
            result = sp.spawn_worker_impl(cwd=None)
        finally:
            patcher.stop()
        self._assert_error(result, calls, "ErrCwdMissing")

    def test_err_cwd_missing_when_cwd_is_empty_string(self):
        """cwd="" triggers ErrCwdMissing (empty string is falsy)."""
        calls, patcher = _patch_tmux([])
        try:
            result = sp.spawn_worker_impl(cwd="")
        finally:
            patcher.stop()
        self._assert_error(result, calls, "ErrCwdMissing")

    # -- ErrCwdNotFound ----------------------------------------------------

    def test_err_cwd_not_found_for_nonexistent_path(self):
        calls, patcher = _patch_tmux([])
        try:
            result = sp.spawn_worker_impl(cwd="/nonexistent/path/unique99991")
        finally:
            patcher.stop()
        self._assert_error(result, calls, "ErrCwdNotFound")

    # -- ErrCwdNotAPath ----------------------------------------------------

    def test_err_cwd_not_a_path_https_url(self):
        calls, patcher = _patch_tmux([])
        try:
            result = sp.spawn_worker_impl(cwd="https://github.com/x/y")
        finally:
            patcher.stop()
        self._assert_error(result, calls, "ErrCwdNotAPath")

    def test_err_cwd_not_a_path_ssh_url(self):
        calls, patcher = _patch_tmux([])
        try:
            result = sp.spawn_worker_impl(cwd="git@github.com:x/y")
        finally:
            patcher.stop()
        self._assert_error(result, calls, "ErrCwdNotAPath")

    def test_err_cwd_not_a_path_relative_path(self):
        calls, patcher = _patch_tmux([])
        try:
            result = sp.spawn_worker_impl(cwd="./relative")
        finally:
            patcher.stop()
        self._assert_error(result, calls, "ErrCwdNotAPath")

    # -- ErrClaudeSettingsNotFound -----------------------------------------

    def test_err_claude_settings_not_found(self):
        calls, patcher = _patch_tmux([])
        try:
            result = sp.spawn_worker_impl(
                cwd="/tmp", claude_settings="/nonexistent_settings.json"
            )
        finally:
            patcher.stop()
        self._assert_error(result, calls, "ErrClaudeSettingsNotFound")

    # -- ErrInstanceIdCollision -------------------------------------------

    def test_err_instance_id_collision(self):
        known_iid = "collision-id-001"
        existing = fake_worker_record(known_iid, "working")
        calls, patcher = _patch_tmux([])
        try:
            with fake_claude_status([_workers_triple_with([existing])]):
                result = sp.spawn_worker_impl(cwd="/tmp", instance_id=known_iid)
        finally:
            patcher.stop()
        self._assert_error(result, calls, "ErrInstanceIdCollision")

    # -- ErrClaudeArgsSettingsConflict ------------------------------------

    def test_err_claude_args_settings_conflict_space_form(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            f.write(b"{}")
            real_path = f.name
        try:
            calls, patcher = _patch_tmux([])
            try:
                result = sp.spawn_worker_impl(
                    cwd="/tmp",
                    claude_args=["--settings", "/x"],
                    claude_settings=real_path,
                )
            finally:
                patcher.stop()
            self._assert_error(result, calls, "ErrClaudeArgsSettingsConflict")
        finally:
            os.unlink(real_path)

    def test_err_claude_args_settings_conflict_equals_form(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            f.write(b"{}")
            real_path = f.name
        try:
            calls, patcher = _patch_tmux([])
            try:
                result = sp.spawn_worker_impl(
                    cwd="/tmp",
                    claude_args=["--settings=/x"],
                    claude_settings=real_path,
                )
            finally:
                patcher.stop()
            self._assert_error(result, calls, "ErrClaudeArgsSettingsConflict")
        finally:
            os.unlink(real_path)

    # -- ErrReservedEnvKey ------------------------------------------------

    def test_err_reserved_env_key_control_env(self):
        calls, patcher = _patch_tmux([])
        try:
            result = sp.spawn_worker_impl(
                cwd="/tmp",
                extra_env={"CLAUDE_STATUS_INSTANCE_ID": "x"},
            )
        finally:
            patcher.stop()
        self._assert_error(result, calls, "ErrReservedEnvKey")

    def test_err_reserved_env_key_label_env(self):
        calls, patcher = _patch_tmux([])
        try:
            result = sp.spawn_worker_impl(
                cwd="/tmp",
                extra_env={"CLAUDE_STATUS_LABEL_CLAUDE_SPAWN_OWNED": "x"},
            )
        finally:
            patcher.stop()
        self._assert_error(result, calls, "ErrReservedEnvKey")

    def test_err_reserved_env_key_home_when_claude_home_set(self):
        calls, patcher = _patch_tmux([])
        try:
            result = sp.spawn_worker_impl(
                cwd="/tmp",
                claude_home="/custom/home",
                extra_env={"HOME": "y"},
            )
        finally:
            patcher.stop()
        self._assert_error(result, calls, "ErrReservedEnvKey")

    # -- ErrThinkingInvalid -----------------------------------------------

    def test_err_thinking_invalid_bad_value(self):
        calls, patcher = _patch_tmux([])
        try:
            result = sp.spawn_worker_impl(cwd="/tmp", thinking="huge")
        finally:
            patcher.stop()
        self._assert_error(result, calls, "ErrThinkingInvalid")

    def test_err_thinking_invalid_description_lists_valid_values(self):
        """err_description must name all four valid thinking values."""
        calls, patcher = _patch_tmux([])
        try:
            result = sp.spawn_worker_impl(cwd="/tmp", thinking="huge")
        finally:
            patcher.stop()
        desc = result.get("err_description", "")
        for valid in ("low", "medium", "high", "xhigh"):
            assert valid in desc, (
                f"valid thinking value {valid!r} not mentioned in err_description: {desc!r}"
            )
