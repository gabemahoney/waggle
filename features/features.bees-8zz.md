---
id: features.bees-8zz
type: subtask
title: Delete tests/scripts/test_config.sh
parent: features.bees-a4i
created_at: '2026-02-11T22:27:07.768950'
updated_at: '2026-02-11T22:48:06.145811'
status: completed
bees_version: '1.1'
---

**Context**: `tests/scripts/test_config.sh` references `scripts/lib/config.sh` which was deleted.

**What to do**:
- Delete `tests/scripts/test_config.sh`
- Check if `tests/scripts/` directory is now empty and can be removed
- Verify no other files reference this script

**Acceptance**: `tests/scripts/test_config.sh` no longer exists.
