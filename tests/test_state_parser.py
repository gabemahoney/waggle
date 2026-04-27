"""Tests for waggle.state_parser — pane content state detection.

Note: In v2, ask_user and check_permission states are set by dedicated relay hooks,
not detected by the parser via set-state. Parser tests are preserved for correctness.
"""

from pathlib import Path

import pytest

from waggle.state_parser import parse

FIXTURES = Path(__file__).parent / "fixtures" / "pane_snapshots"


@pytest.fixture
def working_pane():
    return (FIXTURES / "working.txt").read_text()


@pytest.fixture
def done_pane():
    return (FIXTURES / "done.txt").read_text()


@pytest.fixture
def ask_user_pane():
    return (FIXTURES / "ask_user.txt").read_text()


@pytest.fixture
def ask_user_with_history_pane():
    return (FIXTURES / "ask_user_with_history.txt").read_text()


@pytest.fixture
def check_permission_pane():
    return (FIXTURES / "check_permission.txt").read_text()


@pytest.fixture
def unknown_pane():
    return (FIXTURES / "unknown.txt").read_text()


class TestWorkingState:
    """Tests for Working state detection."""

    def test_working_pane_returns_working_state(self, working_pane):
        """Verify pane with 'Esc to interrupt' is classified as working."""
        state, data = parse(working_pane)
        assert state == "working"

    def test_working_pane_has_no_prompt_data(self, working_pane):
        """Verify working state returns None for prompt_data."""
        _, data = parse(working_pane)
        assert data is None


class TestDoneState:
    """Tests for Done state detection."""

    def test_done_pane_returns_done_state(self, done_pane):
        """Verify pane ending with bare '>' prompt is classified as done."""
        state, data = parse(done_pane)
        assert state == "done"

    def test_done_pane_has_no_prompt_data(self, done_pane):
        """Verify done state returns None for prompt_data."""
        _, data = parse(done_pane)
        assert data is None

    def test_gt_in_output_text_not_done(self):
        """Verify '>' embedded in output text does not trigger done state."""
        content = "Some output\n> this is a blockquote from markdown output\nMore text"
        state, _ = parse(content)
        assert state != "done"

    def test_gt_in_blockquote_output_not_done(self):
        """Verify '>' as blockquote marker in middle of output is not done."""
        content = "Here is the result:\n> Important note: check this\n> Another note\nEnd of output"
        state, _ = parse(content)
        assert state != "done"

    def test_gt_followed_by_text_not_done(self):
        """Verify '>something' is not a done prompt."""
        content = "Processing...\n>not a prompt"
        state, _ = parse(content)
        assert state != "done"


class TestAskUserState:
    """Tests for AskUserQuestion state detection."""

    def test_ask_user_pane_returns_ask_user_state(self, ask_user_pane):
        """Verify pane with ❯ selector and ─── separator is classified as ask_user."""
        state, data = parse(ask_user_pane)
        assert state == "ask_user"

    def test_ask_user_prompt_data_not_none(self, ask_user_pane):
        """Verify ask_user state returns populated prompt_data."""
        _, data = parse(ask_user_pane)
        assert data is not None

    def test_ask_user_question_extracted(self, ask_user_pane):
        """Verify question text is extracted from ask_user pane."""
        _, data = parse(ask_user_pane)
        assert "question" in data
        assert "Are you ready to mark Epic features.bees-lpw as finished?" in data["question"]

    def test_ask_user_options_extracted(self, ask_user_pane):
        """Verify options list is extracted from ask_user pane."""
        _, data = parse(ask_user_pane)
        assert "options" in data
        assert len(data["options"]) == 4

    def test_ask_user_option_numbers(self, ask_user_pane):
        """Verify options have correct sequential numbers."""
        _, data = parse(ask_user_pane)
        numbers = [opt["number"] for opt in data["options"]]
        assert numbers == [1, 2, 3, 4]

    def test_ask_user_option_labels(self, ask_user_pane):
        """Verify option labels are correctly extracted."""
        _, data = parse(ask_user_pane)
        labels = [opt["label"] for opt in data["options"]]
        assert labels[0] == "Yes, mark as finished"
        assert labels[1] == "No, more work needed"
        assert labels[2] == "Type something."
        assert labels[3] == "Chat about this"

    def test_ask_user_option_descriptions(self, ask_user_pane):
        """Verify option descriptions are correctly extracted."""
        _, data = parse(ask_user_pane)
        assert "All acceptance criteria met" in data["options"][0]["description"]
        assert "additional work" in data["options"][1]["description"]

    def test_ask_user_currently_selected(self, ask_user_pane):
        """Verify currently_selected is set to the ❯-highlighted option number."""
        _, data = parse(ask_user_pane)
        assert data["currently_selected"] == 1

    def test_ask_user_navigation_required_above_separator(self, ask_user_pane):
        """Verify options above ─── separator have navigation_required=False."""
        _, data = parse(ask_user_pane)
        for opt in data["options"][:3]:
            assert opt["navigation_required"] is False, (
                f"Option {opt['number']} ({opt['label']}) above separator should not require navigation"
            )

    def test_ask_user_navigation_required_below_separator(self, ask_user_pane):
        """Verify 'Chat about this' below ─── separator has navigation_required=True."""
        _, data = parse(ask_user_pane)
        chat_opt = data["options"][3]
        assert chat_opt["label"] == "Chat about this"
        assert chat_opt["navigation_required"] is True

    def test_numbered_list_in_output_not_ask_user(self):
        """Verify numbered list in plain output does not trigger ask_user state."""
        content = (
            "Here are the steps:\n"
            "1. First do this\n"
            "2. Then do that\n"
            "3. Finally check results\n"
            "Done."
        )
        state, _ = parse(content)
        assert state != "ask_user"

    def test_arrow_without_separator_not_ask_user(self):
        """Verify ❯ alone without ─── separator does not trigger ask_user."""
        content = "Some output\n❯ cursor position\nmore text"
        state, _ = parse(content)
        assert state != "ask_user"

    def test_separator_without_arrow_not_ask_user(self):
        """Verify ─── separator alone without ❯ does not trigger ask_user."""
        content = "Some output\n───────────────\nmore text"
        state, _ = parse(content)
        assert state != "ask_user"

    def test_ask_user_with_history_classified_correctly(self, ask_user_with_history_pane):
        """Verify ask_user state is detected when pane has scrollback with multiple ❯ lines."""
        state, _ = parse(ask_user_with_history_pane)
        assert state == "ask_user"

    def test_ask_user_question_correct_with_history(self, ask_user_with_history_pane):
        """Verify question is extracted from prompt, not from scrollback history."""
        _, data = parse(ask_user_with_history_pane)
        assert data["question"] == "What is your favorite color?"

    def test_ask_user_options_correct_with_history(self, ask_user_with_history_pane):
        """Verify options are parsed correctly when pane has scrollback history."""
        _, data = parse(ask_user_with_history_pane)
        labels = [opt["label"] for opt in data["options"]]
        assert labels == ["Red", "Blue", "Type something.", "Chat about this"]

    def test_ask_user_currently_selected_with_history(self, ask_user_with_history_pane):
        """Verify currently_selected is correct when pane has scrollback with earlier ❯ lines."""
        _, data = parse(ask_user_with_history_pane)
        assert data["currently_selected"] == 1

    def test_ask_user_navigation_required_with_history(self, ask_user_with_history_pane):
        """Verify navigation_required is set correctly when pane has scrollback history."""
        _, data = parse(ask_user_with_history_pane)
        nav_flags = [(opt["label"], opt["navigation_required"]) for opt in data["options"]]
        assert nav_flags == [
            ("Red", False),
            ("Blue", False),
            ("Type something.", False),
            ("Chat about this", True),
        ]


class TestCheckPermissionState:
    """Tests for CheckPermission state detection."""

    def test_check_permission_pane_returns_check_permission_state(self, check_permission_pane):
        """Verify pane with permission prompt is classified as check_permission."""
        state, data = parse(check_permission_pane)
        assert state == "check_permission"

    def test_check_permission_prompt_data_not_none(self, check_permission_pane):
        """Verify check_permission state returns populated prompt_data."""
        _, data = parse(check_permission_pane)
        assert data is not None

    def test_check_permission_tool_type_extracted(self, check_permission_pane):
        """Verify tool type is extracted from check_permission pane."""
        _, data = parse(check_permission_pane)
        assert "tool_type" in data
        assert data["tool_type"] == "Bash command"

    def test_check_permission_command_extracted(self, check_permission_pane):
        """Verify command text is extracted from check_permission pane."""
        _, data = parse(check_permission_pane)
        assert "command" in data
        assert "git log --oneline -5" in data["command"]

    def test_check_permission_description_extracted(self, check_permission_pane):
        """Verify description is extracted from check_permission pane."""
        _, data = parse(check_permission_pane)
        assert "description" in data
        assert "Recent commits" in data["description"]


class TestUnknownState:
    """Tests for Unknown state fallback."""

    def test_unknown_pane_returns_unknown_state(self, unknown_pane):
        """Verify plain shell output with no state markers is classified as unknown."""
        state, data = parse(unknown_pane)
        assert state == "unknown"

    def test_unknown_pane_has_no_prompt_data(self, unknown_pane):
        """Verify unknown state returns None for prompt_data."""
        _, data = parse(unknown_pane)
        assert data is None

    def test_empty_string_returns_unknown(self):
        """Verify empty string input returns unknown state."""
        state, data = parse("")
        assert state == "unknown"
        assert data is None

    def test_whitespace_only_returns_unknown(self):
        """Verify whitespace-only input returns unknown state."""
        state, data = parse("   \n\n   \t  ")
        assert state == "unknown"
        assert data is None


@pytest.fixture
def idle_pane():
    return (FIXTURES / "idle.txt").read_text()


class TestIdlePromptState:
    """Tests for Claude Code idle prompt (❯ with ─── but no options)."""

    def test_idle_claude_prompt_is_done(self, idle_pane):
        """Verify the idle Claude Code prompt is classified as done, not ask_user."""
        state, data = parse(idle_pane)
        assert state == "done"

    def test_idle_claude_prompt_not_ask_user(self, idle_pane):
        """Verify idle prompt with ❯ and ─── but no options does NOT classify as ask_user."""
        state, _ = parse(idle_pane)
        assert state != "ask_user"

    def test_arrow_with_separator_but_no_options_is_done(self):
        """Verify ❯ + ─── without numbered options falls through to done."""
        content = "───────────────────\n❯\n───────────────────\n"
        state, _ = parse(content)
        assert state == "done"


class TestStatePriority:
    """Tests for priority ordering when multiple patterns could match."""

    def test_check_permission_wins_over_ask_user(self):
        """Verify check_permission takes priority over ask_user when both signals present."""
        # Construct content with both check_permission AND ask_user signals
        content = (
            "Do you want to proceed?\n"
            "Permission rule something\n"
            "❯ 1. Yes\n"
            "───────────────\n"
            "  2. No\n"
        )
        state, _ = parse(content)
        assert state == "check_permission"

    def test_check_permission_wins_over_working(self):
        """Verify check_permission takes priority over working state."""
        content = (
            "Bash command\n"
            "\n"
            "  git status\n"
            "\n"
            "Permission rule Bash requires confirmation.\n"
            "\n"
            "Do you want to proceed?\n"
            "❯ 1. Yes\n"
            "  2. No\n"
            "Esc to interrupt\n"
        )
        state, _ = parse(content)
        assert state == "check_permission"

    def test_ask_user_wins_over_working(self):
        """Verify ask_user takes priority over working when both signals present."""
        content = (
            "Question text?\n"
            "\n"
            "❯ 1. Option A\n"
            "───────────────\n"
            "  2. Option B\n"
            "Esc to interrupt\n"
        )
        state, _ = parse(content)
        assert state == "ask_user"

    def test_working_wins_over_done(self):
        """Verify working state takes priority over a trailing > when Esc to interrupt present."""
        content = "Generating output...\nEsc to interrupt\n>\n"
        state, _ = parse(content)
        assert state == "working"
