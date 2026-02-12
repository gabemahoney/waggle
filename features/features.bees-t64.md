---
id: features.bees-t64
type: t2
title: Run unit tests and fix failures
up_dependencies:
- features.bees-rnv
parent: features.bees-28i
created_at: '2026-02-12T08:22:03.451438'
updated_at: '2026-02-12T09:40:14.262660'
status: completed
bees_version: '1.1'
---

Execute the full test suite and fix any failures resulting from the schema refactoring.

**Context**: After schema changes and code refactoring, tests may fail due to schema mismatches, changed behavior, or updated interfaces. All tests must pass before Epic is complete.

**Requirements**:
- Run the full test suite (pytest or similar)
- Identify all failing tests
- Fix each failure by either:
  - Updating test expectations to match new behavior
  - Fixing bugs in implementation code
  - Updating test setup/fixtures for new schema
- Ensure 100% pass rate, even if some failures appear to be pre-existing
- Document any significant issues or edge cases discovered

**Commands**:
```bash
# Run full test suite
pytest tests/ -v

# Or if using different test runner
python -m pytest tests/
```

**Common Failure Causes**:
- Tests using old key format (namespace prefix)
- Tests expecting old schema columns (value instead of repo/status)
- Mock data not matching new schema
- Fixtures not updated for new schema

**Acceptance**:
- All tests pass with 100% success rate
- No skipped or ignored tests
- Test output shows green/passing status
- Any discovered bugs are fixed
