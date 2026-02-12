---
id: features.bees-ejo
type: subtask
title: Remove waggle-validate entry point from pyproject.toml
parent: features.bees-muc
created_at: '2026-02-11T22:26:48.103023'
updated_at: '2026-02-11T22:37:01.238879'
status: completed
bees_version: '1.1'
---

**Context**: The waggle-validate CLI entry point is associated with the dead validate.py module being removed.

**Requirements**:
- Open `pyproject.toml`
- Remove the `waggle-validate` line from the `[tool.poetry.scripts]` section

**Acceptance Criteria**:
- `waggle-validate` no longer appears in pyproject.toml scripts section
- Other scripts remain intact
