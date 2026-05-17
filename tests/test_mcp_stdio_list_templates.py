"""Tests for the list_templates MCP tool (t3.nwq.c4.vr.7e).

Covers SR-7.1 error wrapping and SR-7.2 list-templates contract:
- Empty / missing directory → operation-success with empty lists.
- Valid templates surfaced under templates[] with name, path, options.
- Malformed files surfaced under skipped[] with ErrTemplateMalformed.
- Unexpected exceptions mapped to ErrUnexpected via the FastMCP wrapper.

Uses fake_templates_dir and TEMPLATE_TOML_* constants exclusively.
No TOML string literals are hardcoded here.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

import claude_spawn.mcp_stdio as ms
from tests.helpers import fake_templates_dir
from tests.sample_payloads import (
    TEMPLATE_TOML_FULL,
    TEMPLATE_TOML_MALFORMED_PARSE,
    TEMPLATE_TOML_MINIMAL,
)


# ---------------------------------------------------------------------------
# Case 1 — Empty / missing directory → operation-success with empty lists
# ---------------------------------------------------------------------------


class TestListTemplatesEmptyDir:
    @pytest.mark.asyncio
    async def test_empty_mapping_returns_empty_lists(self):
        """fake_templates_dir({}) — dir exists but has no .toml files."""
        with fake_templates_dir({}):
            result = await ms.list_templates.fn()
        assert result == {"templates": [], "skipped": []}
        assert "ok" not in result or result.get("ok") is not False

    @pytest.mark.asyncio
    async def test_nonexistent_dir_returns_empty_lists(self):
        """_templates_dir points at a path that does not exist."""
        with patch(
            "claude_spawn.templates._templates_dir",
            return_value="/tmp/definitely-does-not-exist-xyz123",
        ):
            result = await ms.list_templates.fn()
        assert result == {"templates": [], "skipped": []}
        assert "ok" not in result or result.get("ok") is not False


# ---------------------------------------------------------------------------
# Case 2 — Valid templates only
# ---------------------------------------------------------------------------


class TestListTemplatesValidOnly:
    @pytest.mark.asyncio
    async def test_two_valid_templates_returned(self):
        """Two valid TOML files → two entries in templates[], none in skipped[]."""
        with fake_templates_dir({"orch": TEMPLATE_TOML_FULL, "mini": TEMPLATE_TOML_MINIMAL}):
            result = await ms.list_templates.fn()

        assert result["skipped"] == []

        entries = result["templates"]
        assert len(entries) == 2

        by_name = {e["name"]: e for e in entries}
        assert set(by_name.keys()) == {"orch", "mini"}

        # Each entry has a path ending in /<name>.toml
        for name, entry in by_name.items():
            assert entry["path"].endswith(f"/{name}.toml"), (
                f"expected path to end with /{name}.toml, got {entry['path']!r}"
            )
            assert isinstance(entry["options"], dict)

        # Spot-check parsed content
        assert by_name["mini"]["options"]["cwd"] == "/tmp"
        assert by_name["orch"]["options"]["cwd"] == "/work/repo"


# ---------------------------------------------------------------------------
# Case 3 — Malformed template skipped, valid template surfaced
# ---------------------------------------------------------------------------


class TestListTemplatesMalformedChannel:
    @pytest.mark.asyncio
    async def test_malformed_skipped_valid_surfaced(self):
        """One parse-error file → skipped[]; one valid file → templates[]."""
        with fake_templates_dir(
            {"bad": TEMPLATE_TOML_MALFORMED_PARSE, "good": TEMPLATE_TOML_MINIMAL}
        ):
            result = await ms.list_templates.fn()

        assert len(result["templates"]) == 1
        assert result["templates"][0]["name"] == "good"

        assert len(result["skipped"]) == 1
        skipped = result["skipped"][0]
        assert skipped["path"].endswith("/bad.toml")
        assert skipped["err_name"] == "ErrTemplateMalformed"
        assert skipped["err_description"]  # non-empty


# ---------------------------------------------------------------------------
# Case 4 — FastMCP error-wrapping: impl raises → ErrUnexpected
# ---------------------------------------------------------------------------


class TestListTemplatesErrorWrapping:
    @pytest.mark.asyncio
    async def test_exception_becomes_err_unexpected(self):
        """Unexpected exception from impl → ok=False, ErrUnexpected, operation=list_templates."""
        with patch(
            "claude_spawn.templates.list_templates_impl",
            side_effect=RuntimeError("boom"),
        ):
            result = await ms.list_templates.fn()

        assert result["ok"] is False
        assert result["err_name"] == "ErrUnexpected"
        assert result["operation"] == "list_templates"
        assert "boom" in result["err_description"]
