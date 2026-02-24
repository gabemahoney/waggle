"""Pure-function state parser for agent pane content.

Classifies raw tmux pane text into agent states without any I/O,
subprocess calls, or waggle imports. Python stdlib only.
"""

import re


def parse(content: str) -> tuple[str, dict | None]:
    """Classify raw pane text content into agent state.

    Detection priority (highest first):
      1. check_permission — permission confirmation prompt
      2. ask_user — interactive question with options
      3. working — agent is actively processing
      4. done — agent is idle at prompt
      5. unknown — fallback

    Args:
        content: Raw text captured from a tmux pane.

    Returns:
        Tuple of (state, prompt_data) where state is one of
        "working", "done", "ask_user", "check_permission", "unknown".
        prompt_data is None for working/done/unknown, a structured dict
        for ask_user/check_permission.
    """
    # 1. check_permission — both markers required
    if "Do you want to proceed?" in content and "Permission rule" in content:
        return "check_permission", _parse_check_permission(content)

    # 2. ask_user — requires BOTH ❯ and ─── AND parsed options to avoid false positives
    if "\u276f" in content and "\u2500\u2500\u2500" in content:
        data = _parse_ask_user(content)
        if data["options"]:
            return "ask_user", data

    # 3. working
    if "Esc to interrupt" in content:
        return "working", None

    # 4. done — standalone > prompt on last non-empty line
    if _is_done(content):
        return "done", None

    # 5. unknown
    return "unknown", None


def _is_done(content: str) -> bool:
    """Check if content shows the agent is at an idle prompt.

    Two patterns qualify:
    - A standalone ❯ on any line (Claude Code idle input box).
    - A standalone > as the last non-empty line (classic shell prompt).
    """
    # Strip ANSI escape codes before checking
    clean = re.sub(r"\x1b\[[0-9;]*m", "", content)
    lines = clean.split("\n")

    # ❯ alone on any line → Claude Code idle prompt
    for line in lines:
        if line.strip() == "\u276f":
            return True

    # > alone as the last non-empty line → shell-style done prompt
    for line in reversed(lines):
        stripped = line.strip()
        if stripped:
            return bool(re.match(r"^>\s*$", stripped))
    return False


def _parse_check_permission(content: str) -> dict:
    """Extract structured data from a check_permission prompt.

    Expected layout:
        <tool_type line>

          <command>
          <description>

        Permission rule ...

        Do you want to proceed?
    """
    lines = content.splitlines()

    perm_idx = next(
        (i for i, line in enumerate(lines) if "Permission rule" in line), None
    )

    tool_type = ""
    command = ""
    description = ""

    if perm_idx is not None:
        # Collect non-blank lines before "Permission rule"
        before = lines[:perm_idx]
        while before and not before[-1].strip():
            before.pop()
        while before and not before[0].strip():
            before.pop(0)

        if before:
            # First non-blank line is tool type
            tool_type = before[0].strip()
            # Remaining non-blank lines: first is command, second is description
            rest = [line.strip() for line in before[1:] if line.strip()]
            if rest:
                command = rest[0]
            if len(rest) > 1:
                description = rest[1]

    return {
        "tool_type": tool_type,
        "command": command,
        "description": description,
    }


def _parse_ask_user(content: str) -> dict:
    """Extract structured data from an ask_user prompt.

    Looks for numbered options prefixed with ❯ or plain digits,
    separated by a ─── horizontal rule.
    """
    lines = content.splitlines()

    # Find the line with ❯ on the same line as a numbered option (e.g. "❯ 1. Yes").
    # This skips history lines like "❯ some previous command" that lack a numbered option.
    arrow_with_opt = re.compile(r"^\s*\u276f\s*\d+\.\s+")
    arrow_idx = next(
        (i for i, line in enumerate(lines) if arrow_with_opt.match(line)), None
    )

    if arrow_idx is None:
        return {"question": "", "options": []}

    # Question: non-blank lines above the first option, skipping intervening blanks
    question_lines = []
    found_text = False
    for i in range(arrow_idx - 1, -1, -1):
        stripped = lines[i].strip()
        if stripped:
            found_text = True
            question_lines.insert(0, stripped)
        elif found_text:
            break
    question = " ".join(question_lines)

    # Parse options from arrow_idx onward
    opt_pattern = re.compile(r"^[\s\u276f]*(\d+)\.\s+(.+)$")
    sep_pattern = re.compile(r"^\s*\u2500{3,}")

    options: list[dict] = []
    i = arrow_idx
    while i < len(lines):
        line = lines[i]

        if sep_pattern.match(line):
            i += 1
            continue

        m = opt_pattern.match(line)
        if m:
            number = int(m.group(1))
            label = m.group(2).strip()
            description = ""

            # Check next line for an indented description
            if i + 1 < len(lines):
                next_line = lines[i + 1]
                next_stripped = next_line.strip()
                if (next_stripped
                        and not opt_pattern.match(next_line)
                        and not sep_pattern.match(next_line)):
                    description = next_stripped
                    i += 1

            options.append({
                "number": number,
                "label": label,
                "description": description,
            })

        i += 1

    return {
        "question": question,
        "options": options,
    }
