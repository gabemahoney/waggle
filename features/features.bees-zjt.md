---
id: features.bees-zjt
type: subtask
title: Delete Config class and load_config function from config.py
down_dependencies:
- features.bees-qwn
- features.bees-5pi
- features.bees-vz2
parent: features.bees-9yk
created_at: '2026-02-11T22:53:14.279649'
updated_at: '2026-02-11T22:54:33.372800'
status: completed
bees_version: '1.1'
---

**Context**: The Config class (lines 13-32) and load_config() function (lines 35-45) in config.py are dead code - never imported or used anywhere in the codebase.

**Requirements**:
- Delete Config class from config.py:13-32
- Delete load_config() function from config.py:35-45
- Verify only get_config() and get_db_path() remain as active functions

**References**: Parent Task features.bees-9yk

**Acceptance**: 
- Config class removed
- load_config() function removed
- File still valid Python
- Only get_config() and get_db_path() remain in config.py
