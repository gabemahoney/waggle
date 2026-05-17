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
import shlex
import tempfile
from unittest.mock import patch

import pytest
import tomli_w

import claude_spawn.spawn as sp
from tests.helpers import (
    fake_claude_status,
    fake_templates_dir,
    fake_worker_record,
    fake_workers_response,
)
from tests.sample_payloads import (
    TEMPLATE_TOML_MALFORMED_PARSE,
    TEMPLATE_TOML_MINIMAL,
)

# ---------------------------------------------------------------------------
# Shared test helpers
# ---------------------------------------------------------------------------

_OK_TRIPLE = ("", "", 0)

# Fixed instance_id for happy-path tests that need a known ID for the
# readiness-loop match and the ErrInstanceIdCollision precheck.
_TEST_IID = "20000000-0000-4000-8000-000000000002"


def _empty_workers_triple() -> tuple[str, str, int]:
    """Canned claude-status triple: success with an empty workers list."""
    payload = json.dumps({"workers": [], "skipped": []})
    return (payload, "", 0)


def _workers_triple_with(records: list[dict]) -> tuple[str, str, int]:
    """Canned claude-status triple: success with a non-empty workers list."""
    payload = json.dumps(fake_workers_response(records))
    return (payload, "", 0)


def _cs_happy_triples(iid: str, cwd: str = "/tmp") -> list[tuple[str, str, int]]:
    """Two-triple list for happy-path tests that supply an explicit instance_id.

    Triple 0: precheck — empty workers (no ErrInstanceIdCollision).
    Triple 1: readiness poll — worker registered on the first poll.
    """
    rec = fake_worker_record(instance_id=iid, status="working", cwd=cwd)
    return [_empty_workers_triple(), _workers_triple_with([rec])]


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
    """Extract the --settings path from a send-keys argv list, or None if absent.

    NOTE: for inline JSON (shell-quoted) values use _extract_settings_value instead.
    This helper is kept for tests that only need to check for absence or compare a
    plain path (e.g. claude_settings-only pass-through).
    """
    cmd = " ".join(send_keys_argv)
    m = re.search(r"--settings(?:=|\s+)(\S+)", cmd)
    return m.group(1) if m else None


def _extract_settings_value(send_keys_argv: list[str]) -> tuple:
    """Extract the --settings value from a send-keys argv list.

    Re-tokenises the joined command via ``shlex.split`` so every quoting form
    ``shlex.quote`` can produce is handled uniformly — including the
    ``'foo'"'"'bar'`` shape that emerges when the quoted string itself
    contains a single quote (e.g. a permission pattern like ``Bash(echo 'x')``).

    Returns:
        (None, None)                     — no --settings flag present
        (parsed_dict, "inline_json")     — value parses as JSON (synthesised overlay)
        (path_str, "path")               — value does not parse as JSON (caller's path)
    """
    tokens = shlex.split(" ".join(send_keys_argv))
    try:
        idx = tokens.index("--settings")
    except ValueError:
        return None, None
    if idx + 1 >= len(tokens):
        return None, None
    value = tokens[idx + 1]
    try:
        return json.loads(value), "inline_json"
    except (json.JSONDecodeError, ValueError):
        return value, "path"


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
            with fake_claude_status(_cs_happy_triples(fixed_iid, cwd)):
                result = sp.spawn_worker_impl(cwd=cwd, instance_id=fixed_iid)
        finally:
            patcher.stop()
        expected = f"{sp._sanitize_folder_name(cwd)}-{fixed_iid[:8]}"
        assert result.get("tmux_session_name") == expected

    def test_short_instance_id_no_padding(self):
        """SR-3.4: instance_id shorter than 8 chars — full string is the suffix."""
        short_iid = "abc"
        cwd = "/tmp"
        rec = fake_worker_record(instance_id=short_iid, status="working", cwd=cwd)
        calls, patcher = _patch_tmux([_OK_TRIPLE, _OK_TRIPLE])
        try:
            with fake_claude_status([_empty_workers_triple(), _workers_triple_with([rec])]):
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
        """Call spawn_worker_impl with patched seams; return (tmux_calls, result).

        Always injects a fixed instance_id so the ErrInstanceIdCollision precheck
        fires (and passes) and the readiness loop finds the worker on the first poll.
        """
        kwargs.setdefault("instance_id", _TEST_IID)
        iid = kwargs["instance_id"]
        cwd = kwargs.get("cwd", "/tmp")
        calls, patcher = _patch_tmux([_OK_TRIPLE, _OK_TRIPLE])
        try:
            with fake_claude_status(_cs_happy_triples(iid, cwd)):
                result = sp.spawn_worker_impl(**kwargs)
        finally:
            patcher.stop()
        return calls, result

    def _run_with_supplied_id(self, instance_id: str = "testid12-0000-0000-0000-000000000000", **kwargs):
        """Like _run, but supply instance_id explicitly (collision check fires + readiness)."""
        cwd = kwargs.get("cwd", "/tmp")
        calls, patcher = _patch_tmux([_OK_TRIPLE, _OK_TRIPLE])
        try:
            with fake_claude_status(_cs_happy_triples(instance_id, cwd)):
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
        _IID = "abc123de-0000-0000-0000-000000000000"
        calls, patcher = _patch_tmux([_OK_TRIPLE, _OK_TRIPLE])
        try:
            with fake_claude_status(_cs_happy_triples(_IID, "/tmp")):
                result = sp.spawn_worker_impl(
                    cwd="/tmp",
                    model="opus",
                    thinking="xhigh",
                    extra_env={"FOO": "bar"},
                    claude_status_labels={"role": "orch"},
                    tmux_session_name="full-test-sess",
                    instance_id=_IID,
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
        kwargs.setdefault("instance_id", _TEST_IID)
        iid = kwargs["instance_id"]
        cwd = kwargs.get("cwd", "/tmp")
        calls, patcher = _patch_tmux([_OK_TRIPLE, _OK_TRIPLE])
        try:
            with fake_claude_status(_cs_happy_triples(iid, cwd)):
                result = sp.spawn_worker_impl(**kwargs)
        finally:
            patcher.stop()
        return calls, result

    def test_neither_supplied_no_settings_flag(self):
        """When neither permissions nor claude_settings supplied, no --settings flag."""
        calls, result = self._run(cwd="/tmp")
        assert _extract_settings_path(calls[1]) is None

    def test_permissions_only_synthesizes_overlay(self):
        """permissions-only: --settings carries shell-quoted inline JSON with exact permissions blob."""
        perms = {"allow": ["Bash"], "deny": ["WebFetch"]}
        calls, result = self._run(cwd="/tmp", permissions=perms)
        value, kind = _extract_settings_value(calls[1])
        assert kind == "inline_json", (
            f"--settings must carry inline JSON, got kind={kind!r}, value={value!r}"
        )
        assert value == {"permissions": perms}

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
        """Composite: per-call permissions.allow overrides file's allow; result is inline JSON."""
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
            value, kind = _extract_settings_value(calls[1])
            assert kind == "inline_json", "--settings must be inline JSON for composite case"
            # Per-call allow wins
            assert value["permissions"]["allow"] == ["Y"]
            # Unrelated top-level key passes through unchanged
            assert value.get("theme") == "dark"
        finally:
            os.unlink(caller_path)

    def test_composite_preserves_file_deny_when_per_call_only_has_allow(self):
        """Composite: file deny preserved when per-call supplies allow only; result is inline JSON."""
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
            value, kind = _extract_settings_value(calls[1])
            assert kind == "inline_json", "--settings must be inline JSON for composite case"
            assert value["permissions"]["allow"] == ["A"]
            assert value["permissions"]["deny"] == ["D"]
        finally:
            os.unlink(caller_path)

    def test_no_tempfile_created_for_permissions_only(self):
        """Regression (b.evz): spawn with permissions must NOT write any claude-spawn-settings-*.json."""
        import glob as _glob
        tmp_dir = tempfile.gettempdir()
        pattern = os.path.join(tmp_dir, "claude-spawn-settings-*.json")
        before = set(_glob.glob(pattern))

        perms = {"allow": ["Bash"]}
        _calls, _result = self._run(cwd="/tmp", permissions=perms)

        after = set(_glob.glob(pattern))
        new_files = after - before
        assert new_files == set(), (
            f"spawn_worker_impl must not write settings tempfiles; found: {new_files}"
        )

    def test_shell_quoting_roundtrip_with_spaces_and_embedded_quotes(self):
        """Shell-quoted inline JSON survives round-trip for permissions containing spaces and embedded quotes."""
        perms = {"allow": ['Bash(echo "hi mom")']}
        calls, result = self._run(cwd="/tmp", permissions=perms)

        # The raw --settings token in the send-keys command must be shell-quoted
        cmd = " ".join(calls[1])
        m = re.search(r"--settings(?:=|\s+)('(?:[^']*)'|\S+)", cmd)
        assert m is not None, "--settings flag must be present"
        raw = m.group(1)
        assert raw.startswith("'"), (
            f"value must be shell-quoted (starts with '): got {raw!r}"
        )

        # Unquoting and JSON-parsing must recover the original permissions intact
        value, kind = _extract_settings_value(calls[1])
        assert kind == "inline_json"
        assert value == {"permissions": perms}, (
            f"round-trip must preserve permissions with embedded quotes: got {value!r}"
        )

    def test_shell_quoting_roundtrip_with_embedded_single_quote(self):
        """Permission patterns containing a single quote survive shlex.quote's
        ``'foo'"'"'bar'`` complex form."""
        perms = {"allow": ["Bash(echo 'hi mom')"]}
        calls, result = self._run(cwd="/tmp", permissions=perms)

        value, kind = _extract_settings_value(calls[1])
        assert kind == "inline_json"
        assert value == {"permissions": perms}, (
            f"round-trip must preserve permissions with embedded single quotes: got {value!r}"
        )

    def test_err_claude_settings_malformed_bad_json(self):
        """Malformed JSON in claude_settings → ErrClaudeSettingsMalformed, no tmux calls."""
        with tempfile.NamedTemporaryFile(
            suffix=".json", mode="w", delete=False
        ) as f:
            f.write('{"permissions": [bad]}')
            bad_path = f.name
        try:
            calls, patcher = _patch_tmux([])
            try:
                result = sp.spawn_worker_impl(
                    cwd="/tmp",
                    claude_settings=bad_path,
                    permissions={"allow": ["X"]},
                )
            finally:
                patcher.stop()
            assert result.get("err_name") == "ErrClaudeSettingsMalformed", (
                f"expected ErrClaudeSettingsMalformed, got {result!r}"
            )
            assert result.get("ok") is False
            assert len(calls) == 0, f"expected no tmux calls; got {calls}"
        finally:
            os.unlink(bad_path)

    def test_err_claude_settings_malformed_permissions_not_dict(self):
        """settings file with permissions as list → ErrClaudeSettingsMalformed, no tmux calls."""
        with tempfile.NamedTemporaryFile(
            suffix=".json", mode="w", delete=False
        ) as f:
            json.dump({"permissions": [1, 2, 3]}, f)
            bad_path = f.name
        try:
            calls, patcher = _patch_tmux([])
            try:
                result = sp.spawn_worker_impl(
                    cwd="/tmp",
                    claude_settings=bad_path,
                    permissions={"allow": ["X"]},
                )
            finally:
                patcher.stop()
            assert result.get("err_name") == "ErrClaudeSettingsMalformed", (
                f"expected ErrClaudeSettingsMalformed, got {result!r}"
            )
            assert result.get("ok") is False
            assert len(calls) == 0, f"expected no tmux calls; got {calls}"
        finally:
            os.unlink(bad_path)


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

    # -- ErrReservedEnvKey (claude_status_labels) -------------------------

    @pytest.mark.parametrize("reserved_key", [
        "claude_spawn_owned",
        "claude_spawn_session_name",
        "claude_spawn_cwd",
        "claude_spawn_model",
    ])
    def test_err_reserved_label_key_rejected(self, reserved_key):
        """claude_status_labels with a reserved key returns ErrReservedEnvKey, no tmux calls."""
        calls, patcher = _patch_tmux([])
        try:
            result = sp.spawn_worker_impl(
                cwd="/tmp",
                claude_status_labels={reserved_key: "0"},
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


# ---------------------------------------------------------------------------
# TestTemplateIntegration — SR-2.x, Epic 3 (12 cases)
# ---------------------------------------------------------------------------


class TestTemplateIntegration:
    """12 template integration cases covering SR-2.x and Epic 3 ACs.

    Every case uses fake_templates_dir (no real ~/.claude-spawn/templates/).
    TOML inputs come from TEMPLATE_TOML_* constants or tomli_w.dumps().
    """

    # ------------------------------------------------------------------
    # Case 1 — bare spawn must not touch the loader
    # ------------------------------------------------------------------

    def test_case_01_bare_spawn_no_read(self):
        """spawn_worker_impl(cwd=...) with no template= must not call _read_template_file."""
        with fake_templates_dir({"orch": TEMPLATE_TOML_MINIMAL}):
            with patch("claude_spawn.templates._read_template_file") as mock_read:
                calls, patcher = _patch_tmux([_OK_TRIPLE, _OK_TRIPLE])
                try:
                    with fake_claude_status(_cs_happy_triples(_TEST_IID)):
                        sp.spawn_worker_impl(cwd="/tmp", instance_id=_TEST_IID)
                finally:
                    patcher.stop()
                mock_read.assert_not_called()

    # ------------------------------------------------------------------
    # Case 2 — happy path: template options reflected in tmux calls
    # ------------------------------------------------------------------

    def test_case_02_happy_path_template_options_reflected(self):
        """Template cwd, model, thinking, extra_env appear in tmux calls."""
        tpl_data = {
            "cwd": "/tmp",
            "model": "opus",
            "thinking": "high",
            "extra_env": {"TPL_FOO": "tpl_bar"},
        }
        with fake_templates_dir({"orch": tomli_w.dumps(tpl_data)}):
            calls, patcher = _patch_tmux([_OK_TRIPLE, _OK_TRIPLE])
            try:
                with fake_claude_status(_cs_happy_triples(_TEST_IID)):
                    result = sp.spawn_worker_impl(cwd=None, template="orch", instance_id=_TEST_IID)
            finally:
                patcher.stop()
        assert result.get("ok") is not False, f"spawn failed: {result}"
        ns_pairs = _env_pairs(calls[0])
        assert ns_pairs.get("CLAUDE_STATUS_LABEL_CLAUDE_SPAWN_MODEL") == "opus"
        assert ns_pairs.get("TPL_FOO") == "tpl_bar"
        cmd = " ".join(calls[1])
        assert "--model opus" in cmd
        assert "--effort high" in cmd

    # ------------------------------------------------------------------
    # Case 3 — per-call scalar overrides template scalar
    # ------------------------------------------------------------------

    def test_case_03_per_call_scalar_overrides_template_scalar(self):
        """Per-call model=sonnet replaces template model=opus wholesale."""
        tpl_data = {"cwd": "/tmp", "model": "opus"}
        with fake_templates_dir({"orch": tomli_w.dumps(tpl_data)}):
            calls, patcher = _patch_tmux([_OK_TRIPLE, _OK_TRIPLE])
            try:
                with fake_claude_status(_cs_happy_triples(_TEST_IID)):
                    result = sp.spawn_worker_impl(
                        cwd="/tmp", template="orch", model="sonnet", instance_id=_TEST_IID
                    )
            finally:
                patcher.stop()
        assert result.get("ok") is not False, f"spawn failed: {result}"
        cmd = " ".join(calls[1])
        assert "--model sonnet" in cmd
        assert "--model opus" not in cmd

    # ------------------------------------------------------------------
    # Case 4 — extra_env map union with per-call wins on collision
    # ------------------------------------------------------------------

    def test_case_04_extra_env_map_union_per_call_wins_on_collision(self):
        """extra_env: per-call BAR=3 wins; template FOO=1 preserved; per-call BAZ=4 added."""
        tpl_data = {"cwd": "/tmp", "extra_env": {"FOO": "1", "BAR": "2"}}
        with fake_templates_dir({"orch": tomli_w.dumps(tpl_data)}):
            calls, patcher = _patch_tmux([_OK_TRIPLE, _OK_TRIPLE])
            try:
                with fake_claude_status(_cs_happy_triples(_TEST_IID)):
                    result = sp.spawn_worker_impl(
                        cwd="/tmp", template="orch",
                        extra_env={"BAR": "3", "BAZ": "4"},
                        instance_id=_TEST_IID,
                    )
            finally:
                patcher.stop()
        assert result.get("ok") is not False, f"spawn failed: {result}"
        pairs = _env_pairs(calls[0])
        assert pairs.get("FOO") == "1", "template-only key FOO must be preserved"
        assert pairs.get("BAR") == "3", "per-call BAR must win on collision"
        assert pairs.get("BAZ") == "4", "per-call-only key BAZ must be present"

    # ------------------------------------------------------------------
    # Case 5 — claude_status_labels union with per-call wins on collision
    # ------------------------------------------------------------------

    def test_case_05_labels_map_union_per_call_wins_on_collision(self):
        """claude_status_labels: per-call role=orch wins; template env=prod preserved."""
        tpl_data = {
            "cwd": "/tmp",
            "claude_status_labels": {"role": "worker", "env": "prod"},
        }
        with fake_templates_dir({"orch": tomli_w.dumps(tpl_data)}):
            calls, patcher = _patch_tmux([_OK_TRIPLE, _OK_TRIPLE])
            try:
                with fake_claude_status(_cs_happy_triples(_TEST_IID)):
                    result = sp.spawn_worker_impl(
                        cwd="/tmp",
                        template="orch",
                        claude_status_labels={"role": "orch", "team": "alpha"},
                        instance_id=_TEST_IID,
                    )
            finally:
                patcher.stop()
        assert result.get("ok") is not False, f"spawn failed: {result}"
        pairs = _env_pairs(calls[0])
        assert pairs.get("CLAUDE_STATUS_LABEL_ROLE") == "orch", "per-call role wins"
        assert pairs.get("CLAUDE_STATUS_LABEL_ENV") == "prod", "template env preserved"
        assert pairs.get("CLAUDE_STATUS_LABEL_TEAM") == "alpha", "per-call team present"

    # ------------------------------------------------------------------
    # Case 6 — permissions map merge: per-call replaces same-key, template
    #           preserves different-key (BOTH halves asserted in one test)
    # ------------------------------------------------------------------

    def test_case_06_permissions_map_merge_dual_assertion(self):
        """Per-call allow=['A'] replaces template allow=['B']; template deny=['D'] preserved."""
        tpl_data = {
            "cwd": "/tmp",
            "permissions": {"allow": ["B"], "deny": ["D"]},
        }
        with fake_templates_dir({"orch": tomli_w.dumps(tpl_data)}):
            calls, patcher = _patch_tmux([_OK_TRIPLE, _OK_TRIPLE])
            try:
                with fake_claude_status(_cs_happy_triples(_TEST_IID)):
                    result = sp.spawn_worker_impl(
                        cwd="/tmp", template="orch",
                        permissions={"allow": ["A"]},
                        instance_id=_TEST_IID,
                    )
            finally:
                patcher.stop()
        assert result.get("ok") is not False, f"spawn failed: {result}"
        value, kind = _extract_settings_value(calls[1])
        assert value is not None, "--settings must be present when permissions used"
        assert kind == "inline_json", "--settings must carry inline JSON when permissions synthesized"
        resolved_perms = value.get("permissions", {})
        # Per-call allow replaces template allow wholesale
        assert resolved_perms.get("allow") == ["A"], (
            f"allow should be ['A'] (per-call wins), got {resolved_perms.get('allow')!r}"
        )
        # Template deny preserved (per-call did not supply deny)
        assert resolved_perms.get("deny") == ["D"], (
            f"deny should be ['D'] (template preserved), got {resolved_perms.get('deny')!r}"
        )

    # ------------------------------------------------------------------
    # Case 7 — list replacement: per-call claude_args replaces template list
    # ------------------------------------------------------------------

    def test_case_07_list_replacement_claude_args(self):
        """Per-call claude_args=['--c'] replaces template ['--a','--b'] wholesale."""
        tpl_data = {"cwd": "/tmp", "claude_args": ["--a", "--b"]}
        with fake_templates_dir({"orch": tomli_w.dumps(tpl_data)}):
            calls, patcher = _patch_tmux([_OK_TRIPLE, _OK_TRIPLE])
            try:
                with fake_claude_status(_cs_happy_triples(_TEST_IID)):
                    result = sp.spawn_worker_impl(
                        cwd="/tmp", template="orch",
                        claude_args=["--c"],
                        instance_id=_TEST_IID,
                    )
            finally:
                patcher.stop()
        assert result.get("ok") is not False, f"spawn failed: {result}"
        cmd = " ".join(calls[1])
        assert "--c" in cmd
        assert "--a" not in cmd
        assert "--b" not in cmd

    # ------------------------------------------------------------------
    # Case 8 — no caching: second call observes mutated file
    # ------------------------------------------------------------------

    def test_case_08_no_caching_second_call_sees_mutated_file(self):
        """SR-6.6: each spawn_worker call re-reads the template file from disk."""
        _IID1 = "case8-call1-0000-4000-8000-000000000001"
        _IID2 = "case8-call2-0000-4000-8000-000000000002"
        tpl_v1 = tomli_w.dumps({"cwd": "/tmp", "model": "opus"})
        tpl_v2 = tomli_w.dumps({"cwd": "/tmp", "model": "sonnet"})
        with fake_templates_dir({"orch": tpl_v1}) as tdir:
            # First call — model from v1 template
            calls1, patcher1 = _patch_tmux([_OK_TRIPLE, _OK_TRIPLE])
            try:
                with fake_claude_status(_cs_happy_triples(_IID1)):
                    result1 = sp.spawn_worker_impl(
                        cwd="/tmp", template="orch", instance_id=_IID1
                    )
            finally:
                patcher1.stop()
            assert result1.get("ok") is not False, f"first spawn failed: {result1}"
            cmd1 = " ".join(calls1[1])
            assert "--model opus" in cmd1, f"expected model=opus in first call: {cmd1!r}"

            # Mutate the on-disk template file
            with open(os.path.join(tdir, "orch.toml"), "w", encoding="utf-8") as fh:
                fh.write(tpl_v2)

            # Second call — must see new content (no caching)
            calls2, patcher2 = _patch_tmux([_OK_TRIPLE, _OK_TRIPLE])
            try:
                with fake_claude_status(_cs_happy_triples(_IID2)):
                    result2 = sp.spawn_worker_impl(
                        cwd="/tmp", template="orch", instance_id=_IID2
                    )
            finally:
                patcher2.stop()
            assert result2.get("ok") is not False, f"second spawn failed: {result2}"
            cmd2 = " ".join(calls2[1])
            assert "--model sonnet" in cmd2, (
                f"expected model=sonnet in second call (no caching): {cmd2!r}"
            )

    # ------------------------------------------------------------------
    # Case 9 — required cwd satisfied by template
    # ------------------------------------------------------------------

    def test_case_09_required_cwd_satisfied_by_template(self):
        """Template supplies cwd=/tmp; per-call omits cwd — spawn succeeds."""
        with fake_templates_dir({"orch": TEMPLATE_TOML_MINIMAL}):
            calls, patcher = _patch_tmux([_OK_TRIPLE, _OK_TRIPLE])
            try:
                with fake_claude_status(_cs_happy_triples(_TEST_IID)):
                    result = sp.spawn_worker_impl(cwd=None, template="orch", instance_id=_TEST_IID)
            finally:
                patcher.stop()
        assert result.get("err_name") is None, (
            f"ErrCwdMissing must not fire when template provides cwd; got {result!r}"
        )
        assert result.get("ok") is not False, f"spawn must succeed; got {result!r}"

    # ------------------------------------------------------------------
    # Case 10 — required cwd NOT satisfied by either source
    # ------------------------------------------------------------------

    def test_case_10_required_cwd_not_satisfied_returns_err_cwd_missing(self):
        """Neither template nor per-call supplies cwd — ErrCwdMissing returned."""
        tpl_no_cwd = tomli_w.dumps({"model": "sonnet"})
        calls, patcher = _patch_tmux([])
        try:
            with fake_templates_dir({"nocwd": tpl_no_cwd}):
                result = sp.spawn_worker_impl(cwd=None, template="nocwd")
        finally:
            patcher.stop()
        assert result.get("err_name") == "ErrCwdMissing", (
            f"expected ErrCwdMissing when neither source provides cwd; got {result!r}"
        )
        assert len(calls) == 0, f"no tmux calls expected before validation error; got {calls}"

    # ------------------------------------------------------------------
    # Case 11 — missing template returns ErrTemplateNotFound
    # ------------------------------------------------------------------

    def test_case_11_missing_template_returns_err_template_not_found(self):
        """ErrTemplateNotFound names both the template name and the templates directory."""
        calls, patcher = _patch_tmux([])
        try:
            with fake_templates_dir({}) as tdir:
                result = sp.spawn_worker_impl(cwd="/tmp", template="nope")
        finally:
            patcher.stop()
        assert result.get("err_name") == "ErrTemplateNotFound", (
            f"expected ErrTemplateNotFound; got {result!r}"
        )
        desc = result.get("err_description", "")
        assert "nope" in desc, f"err_description must name template 'nope': {desc!r}"
        assert tdir in desc, (
            f"err_description must name templates directory {tdir!r}: {desc!r}"
        )
        assert len(calls) == 0, f"no tmux calls expected; got {calls}"

    # ------------------------------------------------------------------
    # Case 12 — malformed template surfaces ErrTemplateMalformed (not remapped)
    # ------------------------------------------------------------------

    def test_case_12_malformed_template_surfaces_err_template_malformed(self):
        """ErrTemplateMalformed from the loader is returned verbatim, not remapped."""
        calls, patcher = _patch_tmux([])
        try:
            with fake_templates_dir({"bad": TEMPLATE_TOML_MALFORMED_PARSE}):
                result = sp.spawn_worker_impl(cwd="/tmp", template="bad")
        finally:
            patcher.stop()
        assert result.get("err_name") == "ErrTemplateMalformed", (
            f"expected ErrTemplateMalformed (not remapped to a per-call error); got {result!r}"
        )
        assert len(calls) == 0, f"no tmux calls expected; got {calls}"

    # ------------------------------------------------------------------
    # Case 13 — empty per-call dict: template-only keys survive
    # ------------------------------------------------------------------

    def test_case_13_empty_per_call_dict_preserves_template_keys(self):
        """Per-call extra_env={} has no entries to override, so template FOO=1 survives.

        SR-2.2 / _merge_maps: an explicit empty per-call dict enters the merge
        path but contributes nothing, so all template-only keys are preserved.
        """
        tpl_data = {"cwd": "/tmp", "extra_env": {"FOO": "1"}}
        with fake_templates_dir({"orch": tomli_w.dumps(tpl_data)}):
            calls, patcher = _patch_tmux([_OK_TRIPLE, _OK_TRIPLE])
            try:
                with fake_claude_status(_cs_happy_triples(_TEST_IID)):
                    result = sp.spawn_worker_impl(
                        cwd="/tmp",
                        template="orch",
                        extra_env={},
                        instance_id=_TEST_IID,
                    )
            finally:
                patcher.stop()
        assert result.get("ok") is not False, f"spawn failed: {result}"
        pairs = _env_pairs(calls[0])
        assert pairs.get("FOO") == "1", (
            "template-only key FOO must survive when per-call extra_env={}"
        )
