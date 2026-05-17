"""Tests for claude_spawn.templates loader and SR-6.4 validation (SR-11.6).

Covers:
- SR-6.4: schema validation rules (unknown key, recursive template, type mismatches)
- SR-6.5: patchable filesystem seams + import-time no-IO guarantee
- enumerate_templates: missing dir, valid entries, mixed valid/error results
- load_template: ErrTemplateNotFound, ErrTemplateMalformed, success cases

No hardcoded TOML string literals — all TOML inputs come from TEMPLATE_TOML_*
constants or programmatic tomli_w construction.
"""

from __future__ import annotations

import importlib
from unittest.mock import MagicMock, patch

import tomli_w
import pytest

import claude_spawn.templates as tmpl
from tests.helpers import fake_templates_dir
from tests.sample_payloads import (
    TEMPLATE_TOML_FULL,
    TEMPLATE_TOML_MALFORMED_PARSE,
    TEMPLATE_TOML_MALFORMED_UNKNOWN_KEY,
    TEMPLATE_TOML_MINIMAL,
    TEMPLATE_TOML_RECURSIVE,
)

# ---------------------------------------------------------------------------
# 1. Missing directory
# ---------------------------------------------------------------------------

_NONEXISTENT_DIR = "/nonexistent/waggle-test-templates-dir-xyz99"


class TestMissingDirectory:
    """_templates_dir points at a path that does not exist."""

    def test_enumerate_yields_zero_entries(self):
        with patch("claude_spawn.templates._templates_dir", return_value=_NONEXISTENT_DIR):
            results = list(tmpl.enumerate_templates())
        assert results == []

    def test_load_template_returns_err_not_found(self):
        with patch("claude_spawn.templates._templates_dir", return_value=_NONEXISTENT_DIR):
            result = tmpl.load_template("any")
        assert result["ok"] is False
        assert result["err_name"] == "ErrTemplateNotFound"

    def test_not_found_description_names_template_and_dir(self):
        with patch("claude_spawn.templates._templates_dir", return_value=_NONEXISTENT_DIR):
            result = tmpl.load_template("my-tpl")
        desc = result["err_description"]
        assert "my-tpl" in desc
        assert _NONEXISTENT_DIR in desc


# ---------------------------------------------------------------------------
# 2. Valid load — minimal
# ---------------------------------------------------------------------------


class TestValidLoadMinimal:
    """Single minimal template (only cwd) loads cleanly."""

    def test_load_template_returns_ok(self):
        with fake_templates_dir({"orch": TEMPLATE_TOML_MINIMAL}):
            result = tmpl.load_template("orch")
        assert result["ok"] is True

    def test_load_template_cwd_value(self):
        with fake_templates_dir({"orch": TEMPLATE_TOML_MINIMAL}):
            result = tmpl.load_template("orch")
        assert result["load_template"]["cwd"] == "/tmp"

    def test_enumerate_yields_one_valid_entry(self):
        with fake_templates_dir({"orch": TEMPLATE_TOML_MINIMAL}):
            results = list(tmpl.enumerate_templates())
        assert len(results) == 1
        name, path, entry = results[0]
        assert name == "orch"
        assert entry["ok"] is True


# ---------------------------------------------------------------------------
# 3. Valid load — full (all SR-1.1 options)
# ---------------------------------------------------------------------------


class TestValidLoadFull:
    """Full template exercises every SR-1.1 option (excluding template)."""

    def _opts(self):
        with fake_templates_dir({"full": TEMPLATE_TOML_FULL}):
            result = tmpl.load_template("full")
        assert result["ok"] is True, f"expected ok=True, got {result!r}"
        return result["load_template"]

    def test_scalars_are_strings(self):
        opts = self._opts()
        for key in ("cwd", "model", "thinking", "tmux_session_name",
                    "instance_id", "claude_home", "claude_settings"):
            assert isinstance(opts[key], str), f"{key} should be str, got {type(opts[key])}"

    def test_maps_are_dicts(self):
        opts = self._opts()
        for key in ("extra_env", "claude_status_labels", "permissions"):
            assert isinstance(opts[key], dict), f"{key} should be dict, got {type(opts[key])}"

    def test_claude_args_is_list_of_strings(self):
        opts = self._opts()
        assert isinstance(opts["claude_args"], list)
        assert all(isinstance(v, str) for v in opts["claude_args"])

    def test_permissions_sub_keys_are_lists(self):
        opts = self._opts()
        for sub in ("allow", "deny", "ask"):
            assert isinstance(opts["permissions"][sub], list), (
                f"permissions.{sub} should be a list"
            )


# ---------------------------------------------------------------------------
# 4. Malformed — TOML parse failure
# ---------------------------------------------------------------------------


class TestMalformedParse:
    """File with invalid TOML syntax is surfaced as ErrTemplateMalformed."""

    def test_load_template_returns_err_malformed(self):
        with fake_templates_dir({"bad": TEMPLATE_TOML_MALFORMED_PARSE}):
            result = tmpl.load_template("bad")
        assert result["ok"] is False
        assert result["err_name"] == "ErrTemplateMalformed"

    def test_enumerate_yields_error_entry(self):
        with fake_templates_dir({"bad": TEMPLATE_TOML_MALFORMED_PARSE}):
            results = list(tmpl.enumerate_templates())
        assert len(results) == 1
        name, path, entry = results[0]
        assert name == "bad"
        assert entry["ok"] is False
        assert entry["err_name"] == "ErrTemplateMalformed"


# ---------------------------------------------------------------------------
# 5. Malformed — unknown top-level key
# ---------------------------------------------------------------------------


class TestMalformedUnknownKey:
    """File with a key outside the SR-1.1 schema is ErrTemplateMalformed."""

    def test_returns_err_malformed(self):
        with fake_templates_dir({"bad": TEMPLATE_TOML_MALFORMED_UNKNOWN_KEY}):
            result = tmpl.load_template("bad")
        assert result["ok"] is False
        assert result["err_name"] == "ErrTemplateMalformed"

    def test_description_names_the_unknown_key(self):
        with fake_templates_dir({"bad": TEMPLATE_TOML_MALFORMED_UNKNOWN_KEY}):
            result = tmpl.load_template("bad")
        assert "not_a_real_option" in result["err_description"]


# ---------------------------------------------------------------------------
# 6. Malformed — recursive (template key present)
# ---------------------------------------------------------------------------


class TestMalformedRecursive:
    """File containing `template = ...` is rejected per SR-2.4 + SR-6.4."""

    def test_returns_err_malformed(self):
        with fake_templates_dir({"bad": TEMPLATE_TOML_RECURSIVE}):
            result = tmpl.load_template("bad")
        assert result["ok"] is False
        assert result["err_name"] == "ErrTemplateMalformed"


# ---------------------------------------------------------------------------
# 7. Malformed — invalid `thinking` value (programmatic via tomli_w)
# ---------------------------------------------------------------------------


class TestMalformedThinking:
    """thinking must be one of low/medium/high/xhigh."""

    def test_invalid_thinking_returns_err_malformed(self):
        body = tomli_w.dumps({"cwd": "/tmp", "thinking": "huge"})
        with fake_templates_dir({"bad": body}):
            result = tmpl.load_template("bad")
        assert result["ok"] is False
        assert result["err_name"] == "ErrTemplateMalformed"

    def test_description_names_all_four_valid_values(self):
        body = tomli_w.dumps({"cwd": "/tmp", "thinking": "huge"})
        with fake_templates_dir({"bad": body}):
            result = tmpl.load_template("bad")
        desc = result["err_description"]
        for valid in ("low", "medium", "high", "xhigh"):
            assert valid in desc, (
                f"valid thinking value {valid!r} not mentioned in description: {desc!r}"
            )


# ---------------------------------------------------------------------------
# 8. Malformed — scalar type mismatch (programmatic via tomli_w)
# ---------------------------------------------------------------------------


class TestMalformedScalarType:
    """Scalar option with non-string value is rejected."""

    def test_cwd_as_int_returns_err_malformed(self):
        body = tomli_w.dumps({"cwd": 123})
        with fake_templates_dir({"bad": body}):
            result = tmpl.load_template("bad")
        assert result["ok"] is False
        assert result["err_name"] == "ErrTemplateMalformed"


# ---------------------------------------------------------------------------
# 9. _read_template_file is a patchable seam
# ---------------------------------------------------------------------------


class TestReadTemplateFileSeam:
    """Loader delegates all file I/O through _read_template_file."""

    def test_loader_uses_read_seam(self):
        known_body = tomli_w.dumps({"cwd": "/seam-test"})
        with fake_templates_dir({"tpl": TEMPLATE_TOML_MINIMAL}):
            with patch(
                "claude_spawn.templates._read_template_file",
                return_value=known_body,
            ) as mock_rf:
                result = tmpl.load_template("tpl")
        assert mock_rf.call_count >= 1, (
            "expected _read_template_file to be called at least once"
        )
        assert result["ok"] is True
        assert result["load_template"]["cwd"] == "/seam-test"


# ---------------------------------------------------------------------------
# 10. Enumerate-all — mixed valid + error result
# ---------------------------------------------------------------------------


class TestEnumerateMixed:
    """One valid + one malformed file; malformed does not abort iteration."""

    def test_both_entries_yielded(self):
        with fake_templates_dir({
            "good": TEMPLATE_TOML_MINIMAL,
            "bad": TEMPLATE_TOML_MALFORMED_PARSE,
        }):
            results = list(tmpl.enumerate_templates())

        assert len(results) == 2, f"expected 2 entries, got {len(results)}: {results}"
        by_name = {name: entry for name, _, entry in results}
        assert by_name["good"]["ok"] is True
        assert by_name["bad"]["ok"] is False
        assert by_name["bad"]["err_name"] == "ErrTemplateMalformed"

    def test_valid_entry_has_expected_cwd(self):
        with fake_templates_dir({
            "good": TEMPLATE_TOML_MINIMAL,
            "bad": TEMPLATE_TOML_MALFORMED_PARSE,
        }):
            results = list(tmpl.enumerate_templates())
        by_name = {name: entry for name, _, entry in results}
        assert by_name["good"]["load_template"]["cwd"] == "/tmp"


# ---------------------------------------------------------------------------
# 11. Import-time no filesystem reads
# ---------------------------------------------------------------------------


class TestImportTimeNoFilesystemReads:
    """Importing claude_spawn.templates must not trigger any filesystem reads."""

    def test_no_io_on_reload(self):
        """Neither _templates_dir nor _read_template_file is called during import."""
        with (
            patch.object(tmpl, "_templates_dir") as mock_td,
            patch.object(tmpl, "_read_template_file") as mock_rf,
        ):
            importlib.reload(tmpl)
            assert mock_td.call_count == 0, (
                "_templates_dir was called during module import"
            )
            assert mock_rf.call_count == 0, (
                "_read_template_file was called during module import"
            )
