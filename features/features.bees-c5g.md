---
id: features.bees-c5g
type: bee
title: Dead code cleanup
labels:
- cleanup
- tech-debt
children:
- features.bees-muc
- features.bees-1qh
- features.bees-a4i
- features.bees-9yk
created_at: '2026-02-11T22:24:41.317988'
updated_at: '2026-02-11T23:00:04.101591'
priority: 2
status: completed
bees_version: '1.1'
---

Remove dead code and fix broken test references identified in code review.

## Work Items

1. **Remove `validate.py` and `waggle-validate` entry point**
   - Delete `src/waggle/validate.py`
   - Remove `waggle-validate` from `pyproject.toml` scripts

2. **Remove unused HTTP config fields from `Config` class**
   - Delete `http_host`, `http_port` parsing in `config.py:26-39`
   - Delete `_validate_host()` method
   - Remove `ipaddress` import

3. **Delete tests for non-existent hooks**
   - Remove fixtures: `stop_hook`, `permission_request_hook`, `notification_hook`, `session_start_hook`
   - Remove `TestHookDescriptiveStates` class
   - Fix `TestConfigReading` tests that use `stop_hook` (use `set_state_hook` instead)

4. **Delete dead test script**
   - Remove `tests/scripts/test_config.sh` (references non-existent `scripts/lib/config.sh`)

5. **Clean up minor dead code**
   - Remove useless `except Exception: raise` in `server.py:50-51`
   - Remove unused `source` variable in `resolve_repo_root`

## Verification

- `poetry run pytest` passes
- `poetry run python -m waggle.server` starts without error
