# Research Findings: b.7XP — libtmux Agent Interaction

## 1. Multi-Pane Support / Claude Agent Teams

**Key finding: Agent Teams operates at the pane level, not the session level.**

- Agent Teams uses `tmux split-window` to create teammate panes within the current window — it does NOT create separate tmux sessions
- Two display modes: `tmux` (split panes) and `in-process` (hidden, navigate with Shift+Up/Down). Default is `auto` (uses split panes if already in tmux)
- This means waggle's current session-level tracking (composite key = `{session_name}+{session_id}+{session_created}`) is insufficient — all teammates share the same session, so they'd overwrite each other's DB entries

**Team lead identification — yes, multiple methods:**

| Method | How | Reliability |
|--------|-----|-------------|
| Config file | `~/.claude/teams/{team-name}/config.json` has `leadAgentId` and `tmuxPaneId` per member | Most reliable |
| Pane position | Team lead is always pane 0 (the original pane before splits) | Reliable |
| Environment vars | Each teammate process sets `CLAUDE_CODE_AGENT_TYPE` = `"team-lead"` | Reliable |

**Sub-agent identification — yes:**
- Each member in config.json has `name`, `agentType`, `tmuxPaneId`, `color`
- Environment variables: `CLAUDE_CODE_AGENT_NAME`, `CLAUDE_CODE_AGENT_ID`, `CLAUDE_CODE_AGENT_TYPE`

**Implication for waggle:** `read_pane` and `send_command` should accept an optional `pane_id` parameter (e.g., `%5`) in addition to `session_id`. For Agent Teams sessions, waggle can read the team config to discover the pane mapping and target the team lead pane specifically.

**Known bugs with tmux mode:** Several open GitHub issues report teammate panes being disconnected from the messaging system or stuck at idle. This is a Claude Code issue, not a waggle issue, but worth noting.

### Sources
- [Official Claude Code Agent Teams Documentation](https://code.claude.com/docs/en/agent-teams)
- [Agent teams should spawn in new tmux window, not split current pane - Issue #23615](https://github.com/anthropics/claude-code/issues/23615)
- [Add configurable tmux split direction for agent team panes - Issue #23950](https://github.com/anthropics/claude-code/issues/23950)
- [teammateMode: "tmux" - split panes disconnected from messaging - Issue #24771](https://github.com/anthropics/claude-code/issues/24771)
- [Agent teams: teammates stuck at idle prompt in tmux split-pane mode - Issue #24108](https://github.com/anthropics/claude-code/issues/24108)
- [Teams tmux mode fails in tcsh/csh: env var syntax not portable - Issue #25375](https://github.com/anthropics/claude-code/issues/25375)
- [Add configuration for separate tmux windows instead of panes - Issue #25396](https://github.com/anthropics/claude-code/issues/25396)

---

## 2. libtmux Capabilities

**Version:** 0.53.0 (Dec 2025), requires Python 3.x and tmux 3.2a+. Pre-1.0, so pin the dependency.

**Object hierarchy:** `Server` → `Session` → `Window` → `Pane` with Django-style `QueryList` filtering on all collections.

**Key operations for waggle:**

| Need | libtmux API | Notes |
|------|------------|-------|
| Read pane content | `pane.capture_pane(start=-50)` | Returns list of strings, supports scrollback range |
| Send text | `pane.send_keys("text", enter=True)` | `enter`, `literal`, `suppress_history` params |
| Create session | `server.new_session(session_name=..., start_directory=..., attach=False)` | Context manager available for auto-cleanup |
| Kill session | `session.kill_session()` | Clean |
| Target pane by ID | `server.panes.get(pane_id="%5")` | Stable targeting for multi-pane |
| Process inspection | `pane.display_message("#{pane_pid}", get_text=True)` | Also `pane_current_command`, `pane_current_path` |
| Session env vars | `session.set_environment("KEY", "val")` | Read back with `session.show_environment()` |
| Error handling | Typed exceptions: `TmuxSessionExists`, `BadSessionName`, etc. | Note: QueryList `.get()` exceptions may not inherit from `LibTmuxException` (known issue #541) |

**Async pattern:** Bundle all synchronous libtmux work into a single function, wrap with `asyncio.to_thread()`:
```python
async def read_pane_async(session_name):
    def _read():
        server = libtmux.Server()
        session = server.sessions.get(session_name=session_name)
        return session.active_window.active_pane.capture_pane()
    return await asyncio.to_thread(_read)
```

**Enhanced functionality ideas:**
- **Tag sessions with env vars at spawn time** (`WAGGLE_AGENT_ID`, `WAGGLE_REPO_ROOT`) for crash-resilient metadata and a secondary source of truth
- **tmux hooks** (`set_hook()`) could detect pane state transitions
- **Resize panes** before capture to ensure UI elements aren't line-wrapped
- **`pipe-pane`** via `pane.cmd()` for logging pane output to a file

### Sources
- [libtmux GitHub Repository](https://github.com/tmux-python/libtmux)
- [libtmux Documentation (v0.53.0)](https://libtmux.git-pull.com/)
- [libtmux on PyPI](https://pypi.org/project/libtmux/)
- [libtmux Panes API](https://libtmux.git-pull.com/api/panes.html)
- [libtmux Pane Interaction Guide](https://libtmux.git-pull.com/topics/pane_interaction.html)
- [libtmux Options and Hooks](https://libtmux.git-pull.com/topics/options_and_hooks.html)
- [libtmux Context Managers](https://libtmux.git-pull.com/topics/context_managers.html)
- [libtmux Exceptions API](https://libtmux.git-pull.com/api/exceptions.html)
- [libtmux QueryList Exception Issue #541](https://github.com/tmux-python/libtmux/issues/541)

---

## 3. LLM Detection in tmux Sessions

**Recommended: 3-layer detection strategy**

| Layer | Method | Role | When to use |
|-------|--------|------|-------------|
| 1 | `pane_current_command` | Direct LLM detection — single tmux call | Always first — trivial and definitive |
| 2 | Waggle DB lookup | Identity, registration, and state info | Cross-reference for registered agents |
| 3 | Pane content heuristics | State classification | Determines Working/Done/AskUser/CheckPermission |

**Primary detection — `pane_current_command` (simplest approach):**

Empirically verified: `tmux list-panes -a -F "#{pane_current_command}"` reports `claude` directly for Claude Code sessions (not `node` or the shell). OpenCode reports as `opencode`. This makes detection trivial:

```bash
tmux list-panes -a -F "#{pane_id} #{pane_current_command}"
# Output: %0 claude, %5 zsh, etc.
```

With libtmux: `pane.pane_current_command` returns `"claude"`, `"opencode"`, `"zsh"`, etc.

No process tree walking needed. No `pgrep`, no `psutil`, no cmdline inspection.

**Fallback — process tree walk (edge cases only):**
- If `pane_current_command` reports the shell (e.g., during agent startup before it takes over the foreground), fall back to `pgrep -P {pane_pid}` + `ps` inspection
- This should be rare in practice

**Stale DB handling:** If DB says agent exists but `pane_current_command` shows a shell (not `claude`/`opencode`) → stale entry, clean it up. If both DB and tmux confirm → agent is genuinely alive.

**Pane content patterns for state detection:**

| State | Detection signal |
|-------|-----------------|
| Working | `Esc to interrupt` text in pane |
| Done | Empty prompt line with `>` at bottom |
| AskUserQuestion | Numbered options with `❯` selector + horizontal rule separator |
| CheckPermission | `Do you want to proceed?` + `Permission rule` text |

### Sources
- [Claude Code GitHub](https://github.com/anthropics/claude-code)
- [@anthropic-ai/claude-code npm package](https://www.npmjs.com/package/@anthropic-ai/claude-code)
- [OpenCode GitHub](https://github.com/opencode-ai/opencode)
- [agent-viewer - Kanban board for Claude Code agents in tmux](https://github.com/hallucinogen/agent-viewer)
- [tmux-agent-indicator - Visual state tracking plugin](https://github.com/accessd/tmux-agent-indicator)
- [Claude Code process forking bug analysis](https://shivankaul.com/blog/claude-code-process-exhaustion)
- [tmux pane_pid process detection via pgrep](https://attie.co.uk/wiki/tmux/find_a_process/)
- [Claude Code hooks reference](https://code.claude.com/docs/en/hooks)

---

## 4. Test Harness Design

**Approach: Unit tests with pre-recorded pane snapshots.**

Capture real Claude Code pane output for each of the 4 states (Working, Done, AskUserQuestion, CheckPermission) and save as text fixtures. Feed these to the state detection parser and assert correct classification. No tmux needed, no API costs, instant.

**Framework:** pytest (already used by the project).

If real tmux capture introduces issues not visible in snapshots (ANSI codes, line wrapping, etc.), add integration-level tests at that point.

### Sources
- [libtmux pytest plugin](https://libtmux.git-pull.com/pytest-plugin/index.html)
- [Claude Code Hooks Reference](https://code.claude.com/docs/en/hooks)
- [Claude Code Permissions](https://code.claude.com/docs/en/permissions)
- [AskUserQuestion Tool Guide](https://www.atcyrus.com/stories/claude-code-ask-user-question-tool-guide)

---

## Open Questions / Risks

1. **Pane-level tracking**: Resolved — hook checks `CLAUDE_CODE_AGENT_TYPE` env var; only team lead (or solo agent) updates the DB. No schema changes needed. Caller manages pane IDs via team config for teammate interaction.
2. **UI pattern fragility**: Claude Code's terminal UI can change between versions. Tier 3 tests serve as canaries.
3. **libtmux stability**: Pre-1.0 library, APIs may break. Pin the version.
4. **`pane_current_command` reliability**: Empirically verified to report `claude` and `opencode` directly. No fallback strategy implemented until proven necessary in practice.
