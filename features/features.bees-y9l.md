---
id: features.bees-y9l
type: bee
title: Code quality improvements
children:
- features.bees-3ym
- features.bees-k6v
- features.bees-giv
- features.bees-d1g
- features.bees-m2j
created_at: '2026-02-11T22:27:30.508679'
updated_at: '2026-02-12T11:31:25.659127'
priority: 3
status: completed
bees_version: '1.1'
---

Remaining code quality issues from code review.

## Work Items

1. **Fix `file://` URI handling** (`server.py:40-43`)
   - Use `urllib.parse.urlparse` + `urllib.parse.unquote` instead of naive string slicing
   - Handles percent-encoded characters (spaces in paths) and `file://localhost/` variants

2. **Reduce test duplication** (`test_server.py`)
   - Extract common mock setup (tmux + DB mocking) into pytest fixtures
   - Currently 1193 lines with ~20 copies of the same mock pattern
   - Target: cut file roughly in half

3. **Extract DB path default constant**
   - Default `~/.waggle/agent_state.db` is computed in 3 places:
     - `config.py:44` (Config.__init__)
     - `config.py:138` (get_db_path)
     - `set_state.sh:15`
   - Extract to module-level constant in Python, document coupling with bash

4. **Clean up `set_state.sh` pipefail usage**
   - `set -o pipefail` is used without `set -e`, so pipeline failures aren't checked
   - Either remove `pipefail` or add explicit error checking after sanitization

5. **Improve SQL injection protection in `set_state.sh`**
   - Currently only escapes single quotes
   - Low severity (local-only tool) but could be more robust

## Verification

- `poetry run pytest` passes
- Test with repo path containing spaces
