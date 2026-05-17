---
id: b.hys
type: bee
title: Rename Waggle → Claude Spawn (repo, package, CLI, code, docs)
down_dependencies:
- b.fkb
- b.dqt
parent: null
children:
- t1.hys.e8
- t1.hys.wp
reference_materials: null
created_at: '2026-05-14T21:38:30.181414'
status: pupa
schema_version: '0.1'
guid: hysb7gijp1s6d1r9dkck57cd67qzgwcx
---

## Idea

Rename the project end-to-end from **Waggle** to **Claude Spawn**. The rename covers the repository name, the Python package, the CLI entry point, the MCP server's advertised name, every code identifier, every documentation reference, every env-var prefix the project owns, and every Claude Status label key the project uses.

The product/identity story changes: "Waggle" was a bee-themed name fitting the Apiary workflow; "Claude Spawn" is more literal — it's the orchestration surface a developer talks to when they want to direct a fleet of Claude Code workers. The rename also moves out of the Apiary naming convention, which is fine because the project's external-facing surface is now stable and operator-facing.

## Why

- "Waggle" is internal jargon that requires explanation. "Claude Spawn" is self-descriptive.
- The post-refactor scope of the project is "I direct Claude workers"; the name should match.
- The rename is best done now, while we're still small (7 source files, fresh contract surface) and while there are essentially no external users to coordinate with.

## In scope

- **Repo / directory layout:** `waggle-project/waggle-main` → `claude-spawn-project/claude-spawn-main`. Worktree convention `waggle-project/b_xxx` → `claude-spawn-project/b_xxx`.
- **Python package:** `src/waggle/` → `src/claude_spawn/`. Module imports updated everywhere.
- **CLI entry point:** `waggle` script → `claude-spawn` (kebab-case per common CLI convention). Subcommands stay: `mcp`, `install`, `sting`.
- **`pyproject.toml`:** `name`, `description`, `packages`, `scripts` entries all renamed.
- **MCP server identity:** the `serverInfo.name` advertised by the stdio MCP server changes from `waggle-stdio` to `claude-spawn-stdio` (or similar).
- **Env vars Waggle injects on spawn:** `CLAUDE_STATUS_LABEL_WAGGLE_*` → `CLAUDE_STATUS_LABEL_CS_*` (short) or `CLAUDE_STATUS_LABEL_CLAUDE_SPAWN_*` (long). The resulting `instances.labels` keys change correspondingly. This is a hard cutover — orchestrators that filter via `--label waggle_owned=1` move to the new key.
- **tmux session name prefix:** default session names change from `waggle-<first8>` to `spawn-<first8>` (or whatever the env-var prefix decision dictates).
- **`sting.py` and any user-facing strings:** update messages, help text, error text.
- **README, architecture docs, migration doc:** rewrite to use the new name throughout. Update repo URL references.
- **Test names and helper modules:** test files renamed where they reference the old name in their filenames; in-test strings updated.

## Out of scope

- **Claude Status changes.** Claude Status has no Waggle-specific knowledge today; it just stores labels. The rename does not require Claude Status code changes. However, if any Claude Status documentation references Waggle by name (e.g. as an example consumer), those references should be updated in a follow-up PR coordinated with Claude Status's release cadence — not in this refactor.
- **Renaming the bee tickets themselves.** Existing bee IDs (`b.m5a`, `b.fg8`, the Epic IDs under `b.fg8`) stay as-is. Commit messages on the rename branch reference them by ID.
- **Functional changes.** No behavioral changes, no new features, no bug fixes. This is a pure rename refactor.
- **Coordinated migration for existing operators.** There are no external operators today; the only Waggle installation is on this dev host. Hard cutover with no compatibility shim.

## Why now

- Post-refactor codebase is at its smallest (7 source files, ~3.8k lines). The rename touches fewer files than it would have last week.
- No external operators to coordinate with.
- The MCP surface is stable; the public contract (six MCP tool names) is what orchestrators bind to and those names are functional, not project-branded, so they don't need to change.
- Renaming earlier is cheaper than renaming later.

## Open questions for the PRD

- **Label prefix length.** `CLAUDE_STATUS_LABEL_CS_*` (short, possibly ambiguous with the shell builtin) vs. `CLAUDE_STATUS_LABEL_CLAUDE_SPAWN_*` (explicit, verbose). Affects: env vars Waggle injects, `labels.*` keys in Claude Status, `--label` filters orchestrators use, label-related code in `spawn.py` / `mcp_stdio.py`. The PRD should pick one.
- **Repo URL / Git remote.** If the repo gets a new GitHub URL, links in README and docs/migration.md update. If not, the local rename is enough. Operator-facing concern, not blocking the code rename.
- **Backwards compatibility for the `waggle` CLI binary.** A thin `waggle` shim that delegates to `claude-spawn` would smooth the cutover for any muscle memory. Cheap to add; explicitly defer to PRD whether to ship one.

## Acceptance criteria

- `git grep -i waggle` in the renamed repo returns zero hits (modulo bee IDs in commit messages, which are immutable history).
- `claude-spawn --help` prints the new name; `claude-spawn mcp` launches the stdio MCP server; `claude-spawn sting` and `claude-spawn install` work.
- A worker spawned via the new MCP server lands in Claude Status with the new label keys; `claude-status workers --label <new_owned_label>=1` returns it.
- `poetry run pytest` is green.
- The README, migration doc, and architecture docs no longer reference "Waggle."
