"""Template I/O and schema validation (SR-6.4, SR-6.5).

This module is the *only* path through which Claude Spawn reads template files.
It owns all filesystem access and all schema validation for ``.toml`` templates.

## Result shape (SR-7.1)

``load_template`` returns a plain ``dict``.  The discriminator is the ``"ok"``
key (``bool``).

Success::

    {
        "ok": True,
        "operation": "load_template",
        "load_template": {<parsed option-map>}
    }

Failure::

    {
        "ok": False,
        "operation": "load_template",
        "err_name": "<ErrName>",
        "err_description": "<human-readable detail>"
    }

## err_name catalogue

- ``ErrTemplateNotFound``  — no ``.toml`` file for the requested template name.
- ``ErrTemplateMalformed`` — the file was found but failed schema validation
  (covers TOML parse errors, unknown keys, forbidden ``template`` key, wrong
  value types, invalid ``thinking`` value).

## Filesystem seams (SR-6.5)

Two private functions are the only entry-points for filesystem access:

- ``_templates_dir()`` — returns the templates directory path.
- ``_read_template_file(path)`` — reads one template file and returns its text.

Tests patch both via ``unittest.mock.patch``:

- ``claude_spawn.templates._templates_dir``
- ``claude_spawn.templates._read_template_file``

## Import inertia (SR-6.5)

``import claude_spawn.templates`` performs no filesystem reads.  Both seams
are called only from the public functions, never at module level.
"""

from __future__ import annotations

import os
import tomllib
from collections.abc import Generator

# ---------------------------------------------------------------------------
# Schema constants (SR-1.1, SR-2.4, SR-6.4)
# ---------------------------------------------------------------------------

_SCALAR_OPTIONS: frozenset[str] = frozenset(
    {"cwd", "model", "thinking", "tmux_session_name", "instance_id",
     "claude_home", "claude_settings"}
)
_MAP_OPTIONS: frozenset[str] = frozenset(
    {"extra_env", "claude_status_labels", "permissions"}
)
_LIST_OPTIONS: frozenset[str] = frozenset({"claude_args"})

_ALLOWED_KEYS: frozenset[str] = _SCALAR_OPTIONS | _MAP_OPTIONS | _LIST_OPTIONS

_THINKING_VALUES: frozenset[str] = frozenset({"low", "medium", "high", "xhigh"})

# ---------------------------------------------------------------------------
# Filesystem seams — patch targets
# ---------------------------------------------------------------------------


def _templates_dir() -> str:
    """Return the templates directory path.

    Patch target: ``claude_spawn.templates._templates_dir``.

    Default: ``~/.claude-spawn/templates`` (expanded via
    ``os.path.expanduser``).  Never called at import time.
    """
    return os.path.expanduser("~/.claude-spawn/templates")


def _read_template_file(path: str) -> str:
    """Read and return the raw text of one template file.

    Patch target: ``claude_spawn.templates._read_template_file``.

    This is the single seam through which all template content enters the
    module.  Never called at import time.
    """
    with open(path, encoding="utf-8") as fh:
        return fh.read()


# ---------------------------------------------------------------------------
# Schema validation helpers
# ---------------------------------------------------------------------------


def _validate(path: str, data: dict) -> str | None:
    """Validate a parsed TOML table against the SR-6.4 schema.

    Returns ``None`` on success, or a human-readable problem string on the
    first validation failure found.
    """
    # SR-2.4 — templates cannot reference templates
    if "template" in data:
        return "key 'template' is not allowed in a template file (SR-2.4)"

    # Unknown keys
    unknown = sorted(set(data) - _ALLOWED_KEYS)
    if unknown:
        return f"unknown key: {unknown[0]}"

    # Scalar options must be strings
    for key in _SCALAR_OPTIONS:
        if key in data and not isinstance(data[key], str):
            got = type(data[key]).__name__
            return f"{key} must be a string, got {got}"

    # thinking must be one of low, medium, high, xhigh
    if "thinking" in data and data["thinking"] not in _THINKING_VALUES:
        return (
            f"thinking must be one of low, medium, high, xhigh; "
            f"got {data['thinking']!r}"
        )

    # Map options must be TOML tables (dicts)
    for key in _MAP_OPTIONS:
        if key in data and not isinstance(data[key], dict):
            got = type(data[key]).__name__
            return f"{key} must be a table, got {got}"

    # List options must be arrays of strings
    for key in _LIST_OPTIONS:
        if key in data:
            val = data[key]
            if not isinstance(val, list):
                got = type(val).__name__
                return f"{key} must be an array of strings, got {got}"
            for i, item in enumerate(val):
                if not isinstance(item, str):
                    got = type(item).__name__
                    return (
                        f"{key}[{i}] must be a string, got {got}"
                    )

    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_template(name: str) -> dict:
    """Resolve, read, and validate a single template by name.

    Returns the parsed option-map dict wrapped in an operation-success result
    on success.  Returns a structured error result for:

    - ``ErrTemplateNotFound`` — no ``.toml`` file exists for *name* in the
      templates directory.  Description names both the template name and the
      templates directory.
    - ``ErrTemplateMalformed`` — the file was found but failed SR-6.4
      validation.  Description names the file path and the specific problem.
    """
    tdir = _templates_dir()
    path = os.path.join(tdir, f"{name}.toml")

    try:
        raw = _read_template_file(path)
    except (FileNotFoundError, OSError):
        return {
            "ok": False,
            "operation": "load_template",
            "err_name": "ErrTemplateNotFound",
            "err_description": (
                f"template {name!r} not found in {tdir!r}"
            ),
        }

    try:
        data = tomllib.loads(raw)
    except tomllib.TOMLDecodeError as exc:
        return {
            "ok": False,
            "operation": "load_template",
            "err_name": "ErrTemplateMalformed",
            "err_description": f"{path}: {exc}",
        }

    problem = _validate(path, data)
    if problem is not None:
        return {
            "ok": False,
            "operation": "load_template",
            "err_name": "ErrTemplateMalformed",
            "err_description": f"{path}: {problem}",
        }

    return {
        "ok": True,
        "operation": "load_template",
        "load_template": data,
    }


def enumerate_templates() -> Generator[tuple[str, str, dict], None, None]:
    """Yield ``(name, path, parsed_options_or_error)`` for each template.

    Scans ``_templates_dir()`` for ``.toml`` files.  For each file:

    - On success: ``parsed_options_or_error`` is the parsed option-map dict
      (i.e. an ``"ok": True`` result).
    - On malformed: ``parsed_options_or_error`` is an ``"ok": False`` result
      with ``err_name="ErrTemplateMalformed"``.  Iteration continues.

    Missing templates directory: yields zero entries with no error.
    """
    tdir = _templates_dir()

    try:
        entries = sorted(os.listdir(tdir))
    except (FileNotFoundError, NotADirectoryError, OSError):
        return

    for filename in entries:
        if not filename.endswith(".toml"):
            continue
        name = filename[:-5]  # strip ".toml"
        path = os.path.join(tdir, filename)

        try:
            raw = _read_template_file(path)
        except OSError as exc:
            yield name, path, {
                "ok": False,
                "operation": "load_template",
                "err_name": "ErrTemplateMalformed",
                "err_description": f"{path}: {exc}",
            }
            continue

        try:
            data = tomllib.loads(raw)
        except tomllib.TOMLDecodeError as exc:
            yield name, path, {
                "ok": False,
                "operation": "load_template",
                "err_name": "ErrTemplateMalformed",
                "err_description": f"{path}: {exc}",
            }
            continue

        problem = _validate(path, data)
        if problem is not None:
            yield name, path, {
                "ok": False,
                "operation": "load_template",
                "err_name": "ErrTemplateMalformed",
                "err_description": f"{path}: {problem}",
            }
            continue

        yield name, path, {
            "ok": True,
            "operation": "load_template",
            "load_template": data,
        }
