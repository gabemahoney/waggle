---
id: b.fg8
type: bee
title: Refactor Waggle to be stateless and ephemeral
up_dependencies:
- b.m5a
parent: null
children:
- t1.fg8.po
- t1.fg8.vv
- t1.fg8.4n
- t1.fg8.fd
- t1.fg8.pr
- t1.fg8.bp
- t1.fg8.2g
reference_materials:
- value: b.m5a
  resolver: bees
created_at: '2026-05-14T15:38:31.290322'
status: done
schema_version: '0.1'
guid: fg8wmr7cdqbdcrg9uwcsk5dt7917ch1r
---

Refactor Waggle to a stateless, ephemeral CLI plus stdio MCP server: delete its SQLite database, retire the daemon and HTTP surface, and reduce its MCP surface to six tmux-focused tools. All worker state, permission decisions, and AUQ records live in Claude Status, which Waggle reaches only through the documented `claude-status` consumer-CLI verbs (`b.oko` contract 1.0.0). See linked Idea Bee b.m5a for the full PRD and SRD.
