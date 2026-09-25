"""A Bash command too long for Git Bash on Windows is refused before it runs.

`.claude/hooks/refuse_long_bash.py`, wired in `.claude/settings.json` as a
PreToolUse hook, answered #1104: a lesson written down in one machine's memory
("write the script, don't heredoc it") failed five more times after it was
recorded, because the sentence named the wrong cause. The cause is length. Of every
Bash call in the ScrapeX transcripts, 14 were longer than 7,500 characters and 12 of
those died mid-parse; every failure was at least 7,930 characters.

WHY THE REFUSAL IS TESTED WITH platform="win32" AND NOT ONLY THROUGH THE SCRIPT.
CI runs on Linux, where the script correctly lets everything through. A test that
only ran the script would therefore check the pass-through branch on CI and never
the branch that refuses. `decide()` takes the platform as an argument so that both
branches run everywhere; the subprocess tests then check the real entry point on
whatever machine runs them.

The `docs` mark is not decoration. CI counts every path under `.claude/` as
documentation, so a change to the hook alone runs only `-m docs`. Without the mark,
the guard would not run on a change to the very thing it guards.
"""
from __future__ import annotations

import importlib.util
import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.docs

ROOT = Path(__file__).resolve().parent.parent
HOOK = ROOT / ".claude" / "hooks" / "refuse_long_bash.py"
SETTINGS = ROOT / ".claude" / "settings.json"

# The failing lengths measured in #1104. A limit that let any of them through
# would be a limit that the evidence already contradicts.
MEASURED_FAILURES = [7930, 7984, 8789, 9008, 9208, 9549, 9684, 9729, 9973, 10569, 11277, 15274]


def _load():
    spec = importlib.util.spec_from_file_location("refuse_long_bash", HOOK)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


hook = _load()


def _bash(command: str) -> dict:
    return {"tool_name": "Bash", "tool_input": {"command": command}}


def test_a_command_at_the_limit_runs():
    assert hook.decide(_bash("x" * hook.LIMIT), "win32") == (0, "")


def test_one_character_over_the_limit_is_refused_and_says_what_to_do_instead():
    code, message = hook.decide(_bash("x" * (hook.LIMIT + 1)), "win32")
    assert code == 2
    assert f"{hook.LIMIT + 1} characters" in message
    assert "Write tool" in message, "the refusal must name the way out, not only the rule"


@pytest.mark.parametrize("length", MEASURED_FAILURES)
def test_every_length_that_failed_in_the_transcripts_is_refused(length):
    code, _ = hook.decide(_bash("x" * length), "win32")
    assert code == 2


def test_a_short_command_runs():
    assert hook.decide(_bash("git status"), "win32") == (0, "")


@pytest.mark.parametrize("platform", ["linux", "darwin"])
def test_a_long_command_runs_where_the_shell_is_not_git_bash_on_windows(platform):
    assert hook.decide(_bash("x" * 20000), platform) == (0, "")


def test_only_the_bash_tool_is_judged():
    """The limit was measured on the Bash tool. A PowerShell command of the same
    length was never measured failing, so it is not refused on a guess."""
    payload = {"tool_name": "PowerShell", "tool_input": {"command": "x" * 20000}}
    assert hook.decide(payload, "win32") == (0, "")


@pytest.mark.parametrize("payload", [
    [],
    {},
    {"tool_name": "Bash"},
    {"tool_name": "Bash", "tool_input": "git status"},
    {"tool_name": "Bash", "tool_input": {}},
    {"tool_name": "Bash", "tool_input": {"command": 5}},
])
def test_an_input_it_cannot_read_is_a_visible_error_and_never_a_refusal(payload):
    """Exit 1 is Claude Code's non-blocking error: the call still runs and the
    transcript shows why the hook could not judge it. Exit 2 here would block every
    Bash call on a malformed input; exit 0 would hide that the guard is blind."""
    code, message = hook.decide(payload, "win32")
    assert code == 1
    assert message.startswith("refuse_long_bash:")


def _run(stdin: bytes) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(HOOK)], input=stdin, capture_output=True,
                          timeout=60, check=False)


def test_the_script_reads_utf8_whatever_the_console_code_page():
    """Windows decodes stdin with the locale's code page unless told otherwise, and
    commands here routinely carry Arabic. A short Arabic command must run; a long one
    must get the same answer as a long ASCII one on this platform."""
    short = json.dumps(_bash("echo 'مرحبا'"), ensure_ascii=False).encode("utf-8")
    assert _run(short).returncode == 0

    long_ = json.dumps(_bash("echo '" + "م" * 8000 + "'"), ensure_ascii=False).encode("utf-8")
    result = _run(long_)
    assert result.returncode == (2 if sys.platform == "win32" else 0), result.stderr


@pytest.mark.parametrize(("arabic_chars", "expected"), [(5000, 0), (8000, 2)])
def test_arabic_is_counted_in_characters_not_in_what_a_code_page_would_see(
        monkeypatch, capsys, arabic_chars, expected):
    """The reachable bug is `sys.stdin.read()`: on a Windows code page it does not
    fail on UTF-8 Arabic, it silently decodes each letter as two characters. A 5,000
    letter command would then count as 10,000 and be refused. Run in-process with a
    code-page stdin and the Windows platform, so this discriminates on every machine,
    CI included, rather than only on the one that has the bug."""
    data = json.dumps(_bash("م" * arabic_chars), ensure_ascii=False).encode("utf-8")
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(data), encoding="cp1252"))
    monkeypatch.setattr(sys, "platform", "win32")
    assert hook.main() == expected, capsys.readouterr().err


def test_stdin_that_is_not_json_is_a_visible_error():
    result = _run(b"not json")
    assert result.returncode == 1
    assert b"not UTF-8 JSON" in result.stderr


def test_the_settings_run_this_script_before_every_bash_call():
    settings = json.loads(SETTINGS.read_text(encoding="utf-8"))
    handlers = [
        handler
        for entry in settings["hooks"]["PreToolUse"]
        if "Bash" in entry.get("matcher", "").split("|")
        for handler in entry["hooks"]
    ]
    script = "${CLAUDE_PROJECT_DIR}/.claude/hooks/refuse_long_bash.py"
    wired = [h for h in handlers if h.get("args") == [script]]
    assert len(wired) == 1, f"expected exactly one handler running the script, found {handlers}"
    assert wired[0]["command"] == "python", (
        "exec form with `python`: on Windows `python3` is the Microsoft Store alias, which "
        "prints 'Python was not found' and exits 49, so the hook would never refuse anything"
    )
    target = Path(wired[0]["args"][0].replace("${CLAUDE_PROJECT_DIR}", str(ROOT)))
    assert target == HOOK and target.is_file()
