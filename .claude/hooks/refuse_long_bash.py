"""Refuse a Bash-tool command too long for Git Bash on Windows to receive whole.

Claude Code runs this before every Bash-tool call (`.claude/settings.json`). On
Windows a command past roughly 7,900 characters arrives cut short and bash fails
mid-parse, sometimes after its first lines already ran. The limit and its evidence
are in #1104: every such failure measured was at least 7,930 characters long.

Exit 2 refuses the call and hands the reason to Claude; exit 0 lets it run; exit 1
is a visible, non-blocking error for an input this script cannot read.
"""
from __future__ import annotations

import json
import sys

LIMIT = 7500

REASON = (
    "Refused: this Bash command is {n} characters, over the {limit} this hook allows. "
    "On Windows, Git Bash receives a command this long cut short and fails mid-parse, "
    "sometimes after running its first lines. Write the payload to a file in the "
    "scratchpad with the Write tool, then run it with one short command, such as "
    "`python <path>`."
)


def decide(payload: object, platform: str) -> tuple[int, str]:
    """The exit code and stderr message for one hook input."""
    if not isinstance(payload, dict) or not isinstance(payload.get("tool_input"), dict):
        return 1, "refuse_long_bash: the hook input has no tool_input object"
    if payload.get("tool_name") != "Bash":
        return 0, ""
    command = payload["tool_input"].get("command")
    if not isinstance(command, str):
        return 1, "refuse_long_bash: tool_input.command is not a string"
    if platform != "win32" or len(command) <= LIMIT:
        return 0, ""
    return 2, REASON.format(n=len(command), limit=LIMIT)


def main() -> int:
    # Bytes, decoded as UTF-8: Claude Code sends UTF-8. Read as text, Windows decodes
    # stdin with the locale's code page, which does not fail on Arabic: it silently
    # counts each letter as two characters and refuses a command half the limit long.
    raw = sys.stdin.buffer.read()
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        print(f"refuse_long_bash: the hook input is not UTF-8 JSON: {exc}", file=sys.stderr)
        return 1
    code, message = decide(payload, sys.platform)
    if message:
        print(message, file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main())
