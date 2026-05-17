"""Tests for the write_template MCP tool (t3.nwq.vv.yc.96).

Covers SR-7.1 error wrapping and SR-7.3 write_template contract:
- Happy path: minimal call → path + options in result, file on disk.
- Options-invalid call → ErrTemplateOptionsInvalid, no file written.
- Collision with force=True → success, content reflects new options.
- Unexpected exception in impl → ErrUnexpected via FastMCP wrapper.

Uses fake_templates_dir and TEMPLATE_TOML_* constants exclusively.
No hardcoded TOML literals.
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

import claude_spawn.mcp_stdio as ms
from tests.helpers import fake_templates_dir
from tests.sample_payloads import TEMPLATE_TOML_MINIMAL


# ---------------------------------------------------------------------------
# Case 1 — Happy path: minimal call
# ---------------------------------------------------------------------------


class TestMinimalCall:
    @pytest.mark.asyncio
    async def test_minimal_call_returns_path_and_options(self):
        """write_template with name + cwd returns path ending in orch.toml + options dict."""
        with fake_templates_dir({}) as tdir:
            result = await ms.write_template.fn(
                name="orch", options={"cwd": "/tmp"}, force=False
            )
        assert "path" in result, f"expected 'path' in result, got {result!r}"
        assert "options" in result, f"expected 'options' in result, got {result!r}"
        assert result["path"].endswith("orch.toml"), (
            f"expected path ending in orch.toml, got {result['path']!r}"
        )
        assert result["options"] == {"cwd": "/tmp"}, (
            f"expected options={{'cwd': '/tmp'}}, got {result['options']!r}"
        )
        assert result.get("ok") is not False, f"result indicates failure: {result!r}"

    @pytest.mark.asyncio
    async def test_minimal_call_file_exists_on_disk(self):
        """The .toml file must be on disk after a successful call."""
        with fake_templates_dir({}) as tdir:
            result = await ms.write_template.fn(
                name="orch", options={"cwd": "/tmp"}, force=False
            )
            assert os.path.exists(result["path"]), (
                f"file not found at {result['path']!r}"
            )


# ---------------------------------------------------------------------------
# Case 2 — Options-invalid call
# ---------------------------------------------------------------------------


class TestOptionsInvalid:
    @pytest.mark.asyncio
    async def test_unknown_option_key_returns_err_options_invalid(self):
        """options with an unknown key → ok=False, ErrTemplateOptionsInvalid, no file."""
        with fake_templates_dir({}) as tdir:
            result = await ms.write_template.fn(
                name="orch", options={"bogus": 1}, force=False
            )
            files_written = os.listdir(tdir)
        assert result.get("ok") is False, f"expected ok=False, got {result!r}"
        assert result["err_name"] == "ErrTemplateOptionsInvalid", (
            f"expected ErrTemplateOptionsInvalid, got {result['err_name']!r}"
        )
        assert "bogus" in result["err_description"], (
            f"expected 'bogus' in description, got {result['err_description']!r}"
        )
        assert files_written == [], (
            f"expected no files written, found {files_written}"
        )


# ---------------------------------------------------------------------------
# Case 3 — Collision with force=True
# ---------------------------------------------------------------------------


class TestCollisionWithForce:
    @pytest.mark.asyncio
    async def test_first_call_succeeds(self):
        """Precondition: first call without force=True must succeed."""
        with fake_templates_dir({}) as tdir:
            result = await ms.write_template.fn(
                name="orch", options={"cwd": "/tmp/v1"}, force=False
            )
        assert result.get("ok") is not False, f"first call failed: {result!r}"

    @pytest.mark.asyncio
    async def test_force_true_overwrites_and_reflects_new_options(self):
        """First call (force=False) then second call (force=True): content = v2."""
        with fake_templates_dir({}) as tdir:
            await ms.write_template.fn(
                name="orch", options={"cwd": "/tmp/v1"}, force=False
            )
            r2 = await ms.write_template.fn(
                name="orch", options={"cwd": "/tmp/v2"}, force=True
            )
            assert r2.get("ok") is not False, f"force=True call failed: {r2!r}"

            # Read raw TOML and confirm v2 content
            path = r2["path"]
            import tomllib
            with open(path, "rb") as fh:
                on_disk = tomllib.load(fh)
        assert on_disk.get("cwd") == "/tmp/v2", (
            f"expected cwd=/tmp/v2 on disk, got {on_disk!r}"
        )


# ---------------------------------------------------------------------------
# Case 4 — FastMCP error wrapping: impl raises → ErrUnexpected
# ---------------------------------------------------------------------------


class TestErrorWrapping:
    @pytest.mark.asyncio
    async def test_unexpected_exception_becomes_err_unexpected(self):
        """Patch write_template_impl to raise; MCP tool must return ErrUnexpected."""
        with patch(
            "claude_spawn.templates.write_template_impl",
            side_effect=RuntimeError("boom"),
        ):
            result = await ms.write_template.fn(
                name="orch", options={"cwd": "/tmp"}, force=False
            )
        assert result["ok"] is False, f"expected ok=False, got {result!r}"
        assert result["err_name"] == "ErrUnexpected", (
            f"expected ErrUnexpected, got {result['err_name']!r}"
        )
        assert "boom" in result["err_description"], (
            f"expected 'boom' in description, got {result['err_description']!r}"
        )
        assert result["operation"] == "write_template", (
            f"expected operation=write_template, got {result.get('operation')!r}"
        )
