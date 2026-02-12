---
id: features.bees-k8p
type: subtask
title: Research and implement more robust SQL sanitization in set_state.sh
down_dependencies:
- features.bees-w4p
- features.bees-j88
- features.bees-6z7
parent: features.bees-m2j
created_at: '2026-02-12T10:51:35.578863'
updated_at: '2026-02-12T11:21:54.257181'
status: completed
bees_version: '1.1'
---

Context: Current implementation only escapes single quotes (sed "s/'/''/g") which is adequate for local-only tool but could be more robust.

What to Do:
- Research bash best practices for SQL injection protection in shell scripts
- Consider options: parameterized queries (not possible with sqlite3 heredoc), better escaping, input validation
- Implement more robust sanitization for SAFE_KEY, SAFE_STATE, and NAMESPACE variables
- Add comments documenting severity (low - local-only tool) and chosen approach

Files: hooks/set_state.sh (lines 37-50)

Acceptance:
- Sanitization handles edge cases beyond single quotes (e.g., null bytes, control characters)
- Code includes inline comments explaining security approach and risk level
- Script still functions correctly with normal inputs
