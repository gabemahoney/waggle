"""Spike test: validate PreToolUse hook on AskUserQuestion supports updatedInput.answers.

This validates the core mechanism that waggle's Permission Relay depends on:
a PreToolUse hook intercepts AskUserQuestion, prints hookSpecificOutput JSON to stdout
with updatedInput.answers, and Claude Code injects that answer so the worker never
blocks at a TUI prompt.

Reference: ~/projects/claude-slack-channel-bots/hooks/ask-relay.sh (bash reference impl)
SRD §5.2 stdout JSON format:
  {"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow",
   "updatedInput":{"answers":{"<question_text>":"<selected_answer>"}}}}

Run manually:
  pytest tests/spikes/test_ask_relay_spike.py -v -s

Requirements:
  - claude CLI installed (claude --version)
  - Valid Claude auth (ANTHROPIC_API_KEY or existing OAuth session)
"""

import json
import stat
import subprocess
from pathlib import Path

import pytest

SENTINEL = "SPIKE_ANSWER_SENTINEL_42"
CLAUDE_TIMEOUT = 60

# Minimal hook script: reads stdin JSON, handles only AskUserQuestion,
# emits hookSpecificOutput with sentinel as the answer.
_HOOK_SCRIPT = f"""\
#!/usr/bin/env python3
import json
import sys

data = json.load(sys.stdin)
if data.get("tool_name") != "AskUserQuestion":
    sys.exit(0)

question = data.get("tool_input", {{}}).get("question", "")
print(json.dumps({{
    "hookSpecificOutput": {{
        "hookEventName": "PreToolUse",
        "permissionDecision": "allow",
        "updatedInput": {{
            "answers": {{question: "{SENTINEL}"}}
        }}
    }}
}}))
"""


@pytest.fixture
def hook_env(tmp_path):
    """Write hook script + settings.json to a temp dir, yield paths."""
    hook_script = tmp_path / "ask_relay_hook.py"
    hook_script.write_text(_HOOK_SCRIPT)
    hook_script.chmod(hook_script.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    settings = {
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "AskUserQuestion",
                    "hooks": [{"type": "command", "command": str(hook_script)}],
                }
            ]
        }
    }
    settings_file = tmp_path / "settings.json"
    settings_file.write_text(json.dumps(settings))

    yield {"hook_script": hook_script, "settings_file": settings_file, "tmp_path": tmp_path}


# ---------------------------------------------------------------------------
# Unit tests — no claude CLI required
# ---------------------------------------------------------------------------


class TestHookScript:
    """Validate the hook script in isolation before running the full integration."""

    def test_outputs_sentinel_for_ask_user_question(self, hook_env):
        """Hook produces valid hookSpecificOutput JSON for AskUserQuestion."""
        hook_script = hook_env["hook_script"]
        tool_input = {
            "tool_name": "AskUserQuestion",
            "tool_input": {
                "question": "What is your favourite colour?",
                "options": [SENTINEL, "wrong_answer"],
            },
        }
        result = subprocess.run(
            [str(hook_script)],
            input=json.dumps(tool_input),
            capture_output=True,
            text=True,
            timeout=5,
        )
        assert result.returncode == 0, f"hook exited {result.returncode}: {result.stderr}"
        output = json.loads(result.stdout)
        hso = output["hookSpecificOutput"]
        assert hso["hookEventName"] == "PreToolUse"
        assert hso["permissionDecision"] == "allow"
        answers = hso["updatedInput"]["answers"]
        assert answers["What is your favourite colour?"] == SENTINEL

    def test_ignores_other_tools(self, hook_env):
        """Hook exits 0 and produces no stdout for non-AskUserQuestion tools."""
        hook_script = hook_env["hook_script"]
        tool_input = {"tool_name": "Bash", "tool_input": {"command": "ls"}}
        result = subprocess.run(
            [str(hook_script)],
            input=json.dumps(tool_input),
            capture_output=True,
            text=True,
            timeout=5,
        )
        assert result.returncode == 0
        assert result.stdout.strip() == ""

    def test_handles_missing_question_gracefully(self, hook_env):
        """Hook emits an answer even if the question field is empty."""
        hook_script = hook_env["hook_script"]
        tool_input = {"tool_name": "AskUserQuestion", "tool_input": {}}
        result = subprocess.run(
            [str(hook_script)],
            input=json.dumps(tool_input),
            capture_output=True,
            text=True,
            timeout=5,
        )
        assert result.returncode == 0
        output = json.loads(result.stdout)
        # answers key is the empty string ""
        answers = output["hookSpecificOutput"]["updatedInput"]["answers"]
        assert "" in answers
        assert answers[""] == SENTINEL


# ---------------------------------------------------------------------------
# Integration test — requires claude CLI + auth
# ---------------------------------------------------------------------------


class TestAskRelayEndToEnd:
    """Full pipeline: claude -p + PreToolUse hook injects sentinel into session."""

    def test_sentinel_injected_via_hook(self, hook_env):
        """The sentinel answer injected by the hook appears in Claude's output.

        Claude is asked to call AskUserQuestion with options that include the sentinel,
        then report back what answer it received. The hook intercepts the call and
        injects SENTINEL. If SENTINEL appears in Claude's printed output, the mechanism
        works end-to-end.

        Note on --settings merge: if the user's global settings.json already has
        PreToolUse hooks for AskUserQuestion (e.g. the real ask-relay.sh), those will
        also fire. The real ask-relay.sh guards itself with a /is-managed check and
        exits 0 when the session is unmanaged, so it won't produce output that
        conflicts with our hook.
        """
        settings_file = hook_env["settings_file"]

        # Ask Claude to call AskUserQuestion with the sentinel as an explicit option,
        # then echo back exactly what answer it received.
        prompt = (
            f"Call the AskUserQuestion tool with question "
            f"'What is the secret passphrase?' and options "
            f"['{SENTINEL}', 'wrong_answer']. "
            f"After you receive the answer, respond with ONLY this exact format: "
            f'"The answer was: <answer>" — no other text.'
        )

        result = subprocess.run(
            [
                "claude",
                "-p", prompt,
                "--settings", str(settings_file),
                "--dangerously-skip-permissions",
            ],
            capture_output=True,
            text=True,
            timeout=CLAUDE_TIMEOUT,
            cwd=str(hook_env["tmp_path"]),
        )

        assert result.returncode == 0, (
            f"claude exited with code {result.returncode}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )
        assert SENTINEL in result.stdout, (
            f"Sentinel '{SENTINEL}' not found in Claude's output — "
            "hook did not successfully inject the answer.\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )

    # -----------------------------------------------------------------------
    # Negative control (informational — skipped by default)
    # -----------------------------------------------------------------------

    @pytest.mark.skip(
        reason=(
            "Negative control: without the hook, AskUserQuestion in -p mode may hang "
            "indefinitely waiting for TUI input. Enable manually to observe the difference."
        )
    )
    def test_no_hook_blocks_or_fails(self, tmp_path):
        """Without a hook, AskUserQuestion in -p mode should block or error."""
        prompt = (
            f"Call the AskUserQuestion tool with question "
            f"'What is the secret passphrase?' and options "
            f"['{SENTINEL}', 'wrong_answer']. "
            f"After you receive the answer, respond with ONLY: "
            f'"The answer was: <answer>".'
        )
        result = subprocess.run(
            ["claude", "-p", prompt, "--dangerously-skip-permissions"],
            capture_output=True,
            text=True,
            timeout=10,  # short timeout — expected to hang or fail
            cwd=str(tmp_path),
        )
        # Expect either non-zero exit or sentinel absent
        assert SENTINEL not in result.stdout, (
            "Sentinel appeared without a hook — unexpected!"
        )
