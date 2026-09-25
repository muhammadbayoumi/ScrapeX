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
    code = hook.main()
    out, err = capsys.readouterr()
    assert code == expected, err
    assert out == "", "Claude Code reads a PreToolUse refusal from stderr; stdout is not the reason"
    if expected == 2:
        assert "Write tool" in err, "the way out must reach Claude, on stderr"


@pytest.mark.parametrize(("stdin", "said"), [
    (b"not json", b"not UTF-8 JSON"),
    (b"[]", b"no tool_input object"),
])
def test_an_unreadable_input_is_reported_on_stderr_and_the_call_runs(stdin, said):
    """The transcript shows the first line of stderr for a non-blocking error, so the
    message is the only way anyone learns the guard was blind for that call."""
    result = _run(stdin)
    assert result.returncode == 1
    assert result.stderr.startswith(b"refuse_long_bash:") and said in result.stderr
    assert result.stdout == b""


SCRIPT_ARG = "${CLAUDE_PROJECT_DIR}/.claude/hooks/refuse_long_bash.py"


def _wired() -> dict:
    settings = json.loads(SETTINGS.read_text(encoding="utf-8"))
    handlers = [
        handler
        for entry in settings["hooks"]["PreToolUse"]
        if "Bash" in entry.get("matcher", "").split("|")
        for handler in entry["hooks"]
    ]
    wired = [h for h in handlers if (h.get("args") or [None])[-1] == SCRIPT_ARG]
    assert len(wired) == 1, f"expected exactly one handler running the script, found {handlers}"
    return wired[0]


def _as_wired(project_dir: Path, stdin: bytes) -> subprocess.CompletedProcess:
    """Run the hook exactly as `.claude/settings.json` launches it, with
    ${CLAUDE_PROJECT_DIR} set to `project_dir`."""
    handler = _wired()
    argv = [sys.executable] + [a.replace("${CLAUDE_PROJECT_DIR}", str(project_dir))
                               for a in handler["args"]]
    return subprocess.run(argv, input=stdin, capture_output=True, timeout=60, check=False)


def test_the_settings_run_this_script_before_every_bash_call():
    handler = _wired()
    assert handler["command"] == "python", (
        "exec form with `python`: on Windows `python3` is the Microsoft Store alias, which "
        "prints 'Python was not found' and exits 49, so the hook would never refuse anything"
    )
    target = Path(SCRIPT_ARG.replace("${CLAUDE_PROJECT_DIR}", str(ROOT)))
    assert target == HOOK and target.is_file()


def test_the_hook_as_wired_answers_exactly_as_the_script_does():
    """The launcher must pass the script's exit code and stderr through untouched."""
    assert _as_wired(ROOT, json.dumps(_bash("git status")).encode()).returncode == 0

    long_ = _as_wired(ROOT, json.dumps(_bash("x" * (hook.LIMIT + 1))).encode())
    if sys.platform == "win32":
        assert long_.returncode == 2 and b"Write tool" in long_.stderr, long_.stderr
    else:
        assert long_.returncode == 0, long_.stderr

    blind = _as_wired(ROOT, b"[]")
    assert blind.returncode == 1 and blind.stderr.startswith(b"refuse_long_bash:")


def test_a_checkout_without_the_script_is_a_visible_error_and_never_a_refusal(tmp_path):
    """Python exits 2 when it cannot open a script, and 2 is the code that refuses. The
    docs say `/cd` applies a directory's hooks while ${CLAUDE_PROJECT_DIR} stays where
    the session started, and one ScrapeX session did start outside the repository and
    move in. Launched directly, a missing file would refuse every Bash call in such a
    session. As wired, it must be exit 1 with a message saying so."""
    result = _as_wired(tmp_path, json.dumps(_bash("git status")).encode())
    assert result.returncode == 1, result.stderr
    assert b"hook script missing" in result.stderr and b"runs unchecked" in result.stderr
