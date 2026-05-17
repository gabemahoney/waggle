"""Tests for claude_spawn.templates.write_template_impl (SR-7.3, SR-7.4).

Covers:
- Minimal success + round-trip through Epic 3 loader
- Full-options round-trip (all SR-1.1 keys except template)
- Collision without force → ErrTemplateExists (file unchanged)
- Collision with force=True → atomic overwrite
- Atomic write resilience: serializer failure leaves canonical unchanged
- Unsafe-name shapes → ErrTemplateNameUnsafe, no file written
- Options validation errors → ErrTemplateOptionsInvalid, no file written
- Directory auto-creation when templates dir is absent

No hardcoded TOML literals — all TOML inputs come from TEMPLATE_TOML_* constants
or programmatic tomli_w construction. No test touches ~/.claude-spawn/templates/.
"""

from __future__ import annotations

import os
import shutil
import tomllib
from unittest.mock import patch

import tomli_w
import pytest

import claude_spawn.templates as tmpl
from claude_spawn.templates import write_template_impl, load_template
from tests.helpers import fake_templates_dir
from tests.sample_payloads import (
    TEMPLATE_TOML_FULL,
    TEMPLATE_TOML_MINIMAL,
)

# Parse the canonical full-options fixture once at module level (no literal TOML here).
_FULL_OPTIONS = tomllib.loads(TEMPLATE_TOML_FULL)

# A nonexistent path we control for the directory-auto-creation test.
_AUTOCREATE_DIR = "/tmp/test-waggle-write-template-autocreate-xyz9871"


# ---------------------------------------------------------------------------
# 1. Minimal success + round-trip
# ---------------------------------------------------------------------------


class TestMinimalSuccessRoundTrip:
    """write_template_impl with only cwd — success, file exists, loads back correctly."""

    def test_returns_ok_with_path_and_options(self):
        with fake_templates_dir({}) as tdir:
            result = write_template_impl("orch", {"cwd": "/tmp"}, force=False)
        assert result["ok"] is True
        assert "path" in result
        assert "options" in result
        assert result["path"].endswith("orch.toml")
        assert result["options"] == {"cwd": "/tmp"}

    def test_file_exists_on_disk(self):
        with fake_templates_dir({}) as tdir:
            result = write_template_impl("orch", {"cwd": "/tmp"}, force=False)
            assert os.path.exists(result["path"])

    def test_round_trip_via_loader(self):
        with fake_templates_dir({}) as tdir:
            write_template_impl("orch", {"cwd": "/tmp"}, force=False)
            loaded = load_template("orch")
        assert loaded["ok"] is True
        assert loaded["load_template"] == {"cwd": "/tmp"}


# ---------------------------------------------------------------------------
# 2. Full-options round-trip
# ---------------------------------------------------------------------------


class TestFullOptionsRoundTrip:
    """All SR-1.1 keys (except template) survive a write → load round-trip."""

    def test_full_options_write_and_load_equal_input(self):
        with fake_templates_dir({}) as tdir:
            result = write_template_impl("full", _FULL_OPTIONS, force=False)
            assert result["ok"] is True, f"expected ok=True, got {result!r}"
            loaded = load_template("full")
        assert loaded["ok"] is True, f"expected loader ok=True, got {loaded!r}"
        assert loaded["load_template"] == _FULL_OPTIONS

    def test_full_options_path_ends_with_full_toml(self):
        with fake_templates_dir({}) as tdir:
            result = write_template_impl("full", _FULL_OPTIONS, force=False)
        assert result["path"].endswith("full.toml")


# ---------------------------------------------------------------------------
# 3. Collision without force
# ---------------------------------------------------------------------------


class TestCollisionWithoutForce:
    """Second write with same name and force=False → ErrTemplateExists, file unchanged."""

    def _first_options(self):
        return {"cwd": "/tmp/v1"}

    def _second_options(self):
        return {"cwd": "/tmp/v2"}

    def test_second_call_returns_err_template_exists(self):
        with fake_templates_dir({}) as tdir:
            write_template_impl("orch", self._first_options(), force=False)
            result2 = write_template_impl("orch", self._second_options(), force=False)
        assert result2["ok"] is False
        assert result2["err_name"] == "ErrTemplateExists"

    def test_description_names_existing_path(self):
        with fake_templates_dir({}) as tdir:
            r1 = write_template_impl("orch", self._first_options(), force=False)
            r2 = write_template_impl("orch", self._second_options(), force=False)
        # The description should mention the path to the existing file.
        assert r1["path"] in r2["err_description"] or "orch.toml" in r2["err_description"]

    def test_file_content_unchanged_after_collision(self):
        with fake_templates_dir({}) as tdir:
            r1 = write_template_impl("orch", self._first_options(), force=False)
            content_after_first = open(r1["path"], "rb").read()
            write_template_impl("orch", self._second_options(), force=False)
            content_after_second = open(r1["path"], "rb").read()
        assert content_after_second == content_after_first


# ---------------------------------------------------------------------------
# 4. Collision with force=True
# ---------------------------------------------------------------------------


class TestCollisionWithForce:
    """Second write with force=True → succeeds and content reflects new options."""

    def test_force_true_returns_ok(self):
        with fake_templates_dir({}) as tdir:
            write_template_impl("orch", {"cwd": "/tmp/v1"}, force=False)
            result2 = write_template_impl("orch", {"cwd": "/tmp/v2"}, force=True)
        assert result2["ok"] is True

    def test_force_true_content_reflects_new_options(self):
        with fake_templates_dir({}) as tdir:
            write_template_impl("orch", {"cwd": "/tmp/v1"}, force=False)
            r2 = write_template_impl("orch", {"cwd": "/tmp/v2"}, force=True)
            assert r2["ok"] is True
            loaded = load_template("orch")
        assert loaded["ok"] is True
        assert loaded["load_template"]["cwd"] == "/tmp/v2"


# ---------------------------------------------------------------------------
# 5. Atomic write resilience
# ---------------------------------------------------------------------------


class TestAtomicWrite:
    """Simulated failure mid-write must leave the canonical file unchanged."""

    def test_serializer_failure_leaves_canonical_unchanged(self):
        """Patch tomli_w.dumps to raise; canonical file from first write survives."""
        with fake_templates_dir({}) as tdir:
            # First write succeeds.
            r1 = write_template_impl("orch", {"cwd": "/tmp/v1"}, force=False)
            assert r1["ok"] is True
            canonical = r1["path"]
            v1_bytes = open(canonical, "rb").read()

            # Force a failure in the serializer on the second (force=True) write.
            with patch("tomli_w.dumps", side_effect=RuntimeError("simulated serializer crash")):
                try:
                    write_template_impl("orch", {"cwd": "/tmp/v2"}, force=True)
                except Exception:
                    pass  # impl may raise or return an error dict; both are acceptable

            # Canonical file must be byte-for-byte unchanged.
            v1_bytes_after = open(canonical, "rb").read()
            assert v1_bytes_after == v1_bytes, (
                "canonical orch.toml was modified despite serializer failure"
            )

    def test_no_leftover_tmp_files_after_failure(self):
        """After a mid-write failure, no *.toml.tmp files should remain in tdir."""
        with fake_templates_dir({}) as tdir:
            write_template_impl("orch", {"cwd": "/tmp/v1"}, force=False)
            with patch("tomli_w.dumps", side_effect=RuntimeError("simulated crash")):
                try:
                    write_template_impl("orch", {"cwd": "/tmp/v2"}, force=True)
                except Exception:
                    pass

            leftover = [f for f in os.listdir(tdir) if f.endswith(".toml.tmp")]
            assert leftover == [], f"leftover temp files after failure: {leftover}"


# ---------------------------------------------------------------------------
# 6. Unsafe-name shapes
# ---------------------------------------------------------------------------


class TestUnsafeNameErrors:
    """Each unsafe-name shape → ErrTemplateNameUnsafe, no file written."""

    _UNSAFE_NAMES = [
        "foo/bar",       # path separator
        ".hidden",       # leading dot
        "..",            # equals ..
        "foo/../escape", # .. substring
        "",              # empty
    ]

    @pytest.mark.parametrize("bad_name", _UNSAFE_NAMES)
    def test_unsafe_name_returns_err_template_name_unsafe(self, bad_name):
        with fake_templates_dir({}) as tdir:
            result = write_template_impl(bad_name, {"cwd": "/tmp"}, force=False)
            files_in_tdir = os.listdir(tdir)
        assert result["ok"] is False, f"expected ok=False for name={bad_name!r}"
        assert result["err_name"] == "ErrTemplateNameUnsafe", (
            f"expected ErrTemplateNameUnsafe for name={bad_name!r}, got {result['err_name']!r}"
        )
        assert files_in_tdir == [], (
            f"expected no files written for unsafe name={bad_name!r}, found {files_in_tdir}"
        )


# ---------------------------------------------------------------------------
# 7. Options validation errors
# ---------------------------------------------------------------------------


class TestOptionsValidationErrors:
    """Invalid options → ErrTemplateOptionsInvalid, description names offender, no file."""

    _INVALID_OPTIONS = [
        ({"bogus": 1},        "bogus"),
        ({"template": "x"},   "template"),
        ({"thinking": "huge"}, "huge"),
        ({"cwd": 123},        "cwd"),
    ]

    @pytest.mark.parametrize("bad_opts,offender", _INVALID_OPTIONS)
    def test_invalid_options_returns_err_template_options_invalid(self, bad_opts, offender):
        with fake_templates_dir({}) as tdir:
            result = write_template_impl("orch", bad_opts, force=False)
            files_in_tdir = os.listdir(tdir)
        assert result["ok"] is False, f"expected ok=False for opts={bad_opts!r}"
        assert result["err_name"] == "ErrTemplateOptionsInvalid", (
            f"expected ErrTemplateOptionsInvalid for opts={bad_opts!r}, got {result['err_name']!r}"
        )
        assert offender in result["err_description"], (
            f"expected {offender!r} in description, got {result['err_description']!r}"
        )
        assert files_in_tdir == [], (
            f"expected no files written for bad opts={bad_opts!r}, found {files_in_tdir}"
        )


# ---------------------------------------------------------------------------
# 8. Directory auto-creation
# ---------------------------------------------------------------------------


class TestDirectoryAutoCreation:
    """write_template_impl creates the templates directory if it does not exist."""

    def setup_method(self):
        """Ensure the test directory does not exist before each test."""
        if os.path.exists(_AUTOCREATE_DIR):
            shutil.rmtree(_AUTOCREATE_DIR)

    def teardown_method(self):
        """Clean up the test directory after each test."""
        if os.path.exists(_AUTOCREATE_DIR):
            shutil.rmtree(_AUTOCREATE_DIR)

    def test_missing_dir_gets_created(self):
        assert not os.path.exists(_AUTOCREATE_DIR), "test dir already exists before test"
        with patch("claude_spawn.templates._templates_dir", return_value=_AUTOCREATE_DIR):
            result = write_template_impl("x", {"cwd": "/tmp"}, force=False)
        assert result["ok"] is True
        assert os.path.isdir(_AUTOCREATE_DIR), "templates directory was not auto-created"

    def test_file_written_in_new_dir(self):
        with patch("claude_spawn.templates._templates_dir", return_value=_AUTOCREATE_DIR):
            result = write_template_impl("x", {"cwd": "/tmp"}, force=False)
        assert result["ok"] is True
        expected_path = os.path.join(_AUTOCREATE_DIR, "x.toml")
        assert os.path.exists(expected_path), f"expected file at {expected_path}"
