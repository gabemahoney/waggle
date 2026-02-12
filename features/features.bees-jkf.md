---
id: features.bees-jkf
type: t2
title: Review unit tests for this Epic. See if you need to update, delete or add any.
up_dependencies:
- features.bees-2iq
down_dependencies:
- features.bees-j3b
parent: features.bees-fp8
created_at: '2026-02-11T23:39:48.518194'
updated_at: '2026-02-11T23:44:03.281655'
status: closed
bees_version: '1.1'
---

Review and update unit tests for cleanup_dead_sessions() duplicate removal functionality.

**Context**: New duplicate detection logic added to cleanup_dead_sessions(). Need tests to validate duplicate removal.

**Requirements**:
- Locate existing tests for cleanup_dead_sessions() in test suite
- Add test case for duplicate entry scenario:
  - Create multiple state entries with same composite key but different namespaces
  - Run cleanup_dead_sessions()
  - Verify only entry with max ROWID remains
  - Verify duplicate entries are deleted
- Test edge cases: no duplicates, all entries duplicate, single entry
- Ensure all cleanup_dead_sessions() tests pass

**Acceptance**: Test coverage includes duplicate detection/removal with edge cases validated.

**Parent Epic**: features.bees-fp8
