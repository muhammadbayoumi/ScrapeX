"""How often a memory lesson broke again after it was written down is counted.

`tools/recurrence_scan.py` answers #1104 option 3: the counter a "second failure gets
a barrier" rule needs. A lesson's note never records its own recurrences, so the only
honest count comes from the session transcripts. These tests build a memory folder and
a projects folder of transcripts in the shapes Claude Code writes, and check every
branch that decides a number in the report.

WHY "RECORDED" IS THE FIRST WRITE AND NOT `metadata.modified`. The memory system moves
`modified` on every edit, so a lesson corrected today would appear to start today and
every earlier recurrence would count as "before". The first Write of the file in a
transcript is when the lesson began.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import recurrence_scan as rs  # noqa: E402

T0, T1, T2, T3 = ("2026-09-10T10:00:00.000Z", "2026-09-12T10:00:00.000Z",
                  "2026-09-14T10:00:00.000Z", "2026-09-16T10:00:00.000Z")
PARSE_ERROR = "bash: -c: line 3: unexpected EOF while looking for matching `''"


def _note(memory: Path, name: str, signature: str | None = None, *, body: str = "text") -> Path:
    meta = "metadata:\n  type: feedback\n  modified: 2026-09-20T00:00:00.000Z\n"
    if signature is not None:
        meta += "  failure_signature:\n" + "".join(f"    {line}\n" for line in signature.splitlines())
    path = memory / f"{name}.md"
    path.write_text(f"---\nname: {name}\ndescription: d\n{meta}---\n\n{body}\n", encoding="utf-8")
    return path


class Transcript:
    """One .jsonl file, written the way Claude Code writes a session."""

    def __init__(self, path: Path):
        self.path = path
        self.lines: list[str] = []
        self.n = 0

    def call(self, when: str, tool: str, given: dict, result: str) -> Transcript:
        self.n += 1
        use_id = f"toolu_{self.path.stem}_{self.n}"
        self.lines.append(json.dumps({"type": "assistant", "timestamp": when, "message": {
            "role": "assistant", "content": [{"type": "tool_use", "id": use_id, "name": tool, "input": given}]}}))
        self.lines.append(json.dumps({"type": "user", "timestamp": when, "message": {
            "role": "user", "content": [{"type": "tool_result", "tool_use_id": use_id,
                                         "content": [{"type": "text", "text": result}]}]}}))
        return self

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("\n".join(self.lines) + "\n", encoding="utf-8")


@pytest.fixture()
def world(tmp_path):
    projects = tmp_path / "projects"
    memory = projects / "C--x-ScrapeX" / "memory"
    memory.mkdir(parents=True)
    return projects, memory


def _run(projects: Path, memory: Path, *extra: str):
    return rs.main(["--projects", str(projects), "--memory", str(memory), *extra])


HEREDOC = "result: 'unexpected EOF while looking for matching'"


def test_a_failure_is_counted_before_and_after_the_first_write_of_the_note(world, capsys):
    projects, memory = world
    note = _note(memory, "heredoc", HEREDOC)
    main = projects / "C--x-ScrapeX--claude-worktrees-a"
    Transcript(main / "s1.jsonl").call(T0, "Bash", {"command": "python - <<'PY'"}, PARSE_ERROR) \
        .call(T1, "Write", {"file_path": str(note)}, "File created").save()
    Transcript(main / "s2.jsonl").call(T2, "Bash", {"command": "x"}, PARSE_ERROR).save()
    Transcript(main / "s3.jsonl").call(T3, "Bash", {"command": "y"}, PARSE_ERROR) \
        .call(T3, "Bash", {"command": "z"}, "fine").save()

    assert _run(projects, memory, "--json") == 0
    row = json.loads(capsys.readouterr().out)[0]
    assert (row["before"], row["after"], row["sessions_after"]) == (1, 2, ["s2", "s3"])
    assert row["recorded"].startswith("2026-09-12") and row["recorded_from"] == "first write in a transcript"


def test_two_failures_after_recording_flag_a_barrier_candidate_and_one_does_not(world, capsys):
    projects, memory = world
    twice = _note(memory, "twice", HEREDOC)
    once = _note(memory, "once", "result: 'no such thing'")
    Transcript(projects / "C--x-ScrapeX" / "s1.jsonl") \
        .call(T0, "Write", {"file_path": str(twice)}, "ok").call(T0, "Write", {"file_path": str(once)}, "ok") \
        .call(T1, "Bash", {"command": "a"}, PARSE_ERROR).call(T2, "Bash", {"command": "b"}, PARSE_ERROR) \
        .call(T2, "Bash", {"command": "c"}, "no such thing").save()

    assert _run(projects, memory) == 0
    lines = capsys.readouterr().out.splitlines()
    assert any(line.startswith("twice") and line.endswith("barrier candidate") for line in lines)
    assert any(line.startswith("once") and "barrier" not in line for line in lines)


def test_a_shape_is_counted_and_never_flagged(world, capsys):
    """A shape is the form a lesson forbids, not evidence it broke: never a candidate."""
    projects, memory = world
    note = _note(memory, "piped", "command: '\\bpytest\\b[^|;&]*\\|\\s*tail'")
    t = Transcript(projects / "C--x-ScrapeX" / "s1.jsonl").call(T0, "Write", {"file_path": str(note)}, "ok")
    for when in (T1, T2, T3):
        t.call(when, "Bash", {"command": "pytest -q | tail -3"}, "5 passed")
    t.save()

    assert _run(projects, memory) == 0
    line = next(x for x in capsys.readouterr().out.splitlines() if x.startswith("piped"))
    assert " shape " in line and line.split()[4] == "3" and "barrier" not in line


def test_the_tool_filter_decides_which_calls_a_signature_reads(world, capsys):
    projects, memory = world
    bash = _note(memory, "bash-only", "tool: Bash\nresult: 'boom'")
    shell = _note(memory, "shell", "result: 'boom'")
    anything = _note(memory, "any-tool", "tool: any\nresult: 'boom'")
    t = Transcript(projects / "C--x-ScrapeX" / "s1.jsonl")
    for note in (bash, shell, anything):
        t.call(T0, "Write", {"file_path": str(note)}, "ok")
    t.call(T1, "Bash", {"command": "a"}, "boom").call(T1, "PowerShell", {"command": "b"}, "boom") \
        .call(T1, "Read", {"file_path": "c"}, "boom").save()

    assert _run(projects, memory, "--json") == 0
    after = {r["lesson"]: r["after"] for r in json.loads(capsys.readouterr().out)}
    assert after == {"bash-only": 1, "shell": 2, "any-tool": 3}


def test_a_subagent_transcript_counts_for_the_session_that_ran_it(world, capsys):
    projects, memory = world
    note = _note(memory, "heredoc", HEREDOC)
    folder = projects / "C--x-ScrapeX"
    Transcript(folder / "parent.jsonl").call(T0, "Write", {"file_path": str(note)}, "ok").save()
    Transcript(folder / "parent" / "subagents" / "workflows" / "wf_1" / "agent-a.jsonl") \
        .call(T1, "Bash", {"command": "x"}, PARSE_ERROR).save()

    assert _run(projects, memory, "--json") == 0
    assert json.loads(capsys.readouterr().out)[0]["sessions_after"] == ["parent"]


def test_only_this_projects_transcripts_are_read(world, capsys):
    projects, memory = world
    note = _note(memory, "heredoc", HEREDOC)
    Transcript(projects / "C--x-ScrapeX" / "s1.jsonl").call(T0, "Write", {"file_path": str(note)}, "ok").save()
    Transcript(projects / "C--x-other-project" / "s2.jsonl").call(T1, "Bash", {"command": "x"}, PARSE_ERROR).save()
    Transcript(projects / "C--x-ScrapeX" / "s1" / "journal.jsonl").call(T1, "Bash", {"command": "x"}, PARSE_ERROR).save()

    assert _run(projects, memory, "--json") == 0
    assert json.loads(capsys.readouterr().out)[0]["after"] == 0


def test_a_note_never_written_in_a_transcript_falls_back_to_its_creation_time_and_says_so(world, capsys):
    projects, memory = world
    _note(memory, "old-lesson", HEREDOC)
    Transcript(projects / "C--x-ScrapeX" / "s1.jsonl").call(T1, "Bash", {"command": "x"}, PARSE_ERROR).save()

    assert _run(projects, memory) == 0
    out = capsys.readouterr().out
    assert "recorded time from file creation, not a transcript: old-lesson" in out


@pytest.mark.parametrize(("signature", "said"), [
    ("result: '(unclosed'", "result is not a valid regex"),
    ("kind: failure\ncommand: 'x'", "a failure signature needs a result pattern"),
    ("tool: Bash", "needs a command or a result pattern"),
    ("result: 'x'\nwhen: always", "unknown keys"),
    ("kind: sometimes\nresult: 'x'", "kind must be failure or shape"),
    ("result: ''", "result is not a non-empty string"),
    ("result: 'x'\ncaveat: 3", "caveat is not a string"),
])
def test_an_unreadable_signature_is_reported_by_name_and_the_rest_still_scan(world, capsys, signature, said):
    projects, memory = world
    _note(memory, "broken", signature)
    good = _note(memory, "good", HEREDOC)
    Transcript(projects / "C--x-ScrapeX" / "s1.jsonl").call(T0, "Write", {"file_path": str(good)}, "ok") \
        .call(T1, "Bash", {"command": "x"}, PARSE_ERROR).save()

    assert _run(projects, memory) == 0
    out = capsys.readouterr().out
    assert "UNREADABLE SIGNATURE broken: " in out and said in out
    assert any(line.startswith("good") and line.split()[4] == "1" for line in out.splitlines())


def test_a_signature_that_is_not_a_mapping_is_unreadable(world, capsys):
    projects, memory = world
    (memory / "flat.md").write_text(
        "---\nname: flat\nmetadata:\n  failure_signature: 'just a string'\n---\n\nx\n", encoding="utf-8")
    Transcript(projects / "C--x-ScrapeX" / "s1.jsonl").call(T1, "Bash", {"command": "x"}, "y").save()
    assert _run(projects, memory) == 0
    assert "UNREADABLE SIGNATURE flat: failure_signature is not a mapping" in capsys.readouterr().out


def test_notes_without_a_signature_are_named_as_unmeasured_and_the_index_is_skipped(world, capsys):
    projects, memory = world
    _note(memory, "semantic-lesson")
    (memory / "MEMORY.md").write_text("- index\n", encoding="utf-8")
    Transcript(projects / "C--x-ScrapeX" / "s1.jsonl").call(T1, "Bash", {"command": "x"}, "y").save()

    assert _run(projects, memory) == 0
    assert "0 lessons measured, 1 with no failure_signature: semantic-lesson" in capsys.readouterr().out


@pytest.mark.parametrize("setup", ["no transcripts", "no tool calls"])
def test_an_empty_scan_is_an_error_about_the_scanner_not_a_clean_report(world, capsys, setup):
    """"Nothing recurred" and "I read nothing" must never print the same thing."""
    projects, memory = world
    _note(memory, "heredoc", HEREDOC)
    if setup == "no tool calls":
        path = projects / "C--x-ScrapeX" / "s1.jsonl"
        path.write_text(json.dumps({"type": "user", "message": {"content": "hello"}}) + "\n", encoding="utf-8")

    assert _run(projects, memory) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "not evidence that nothing recurred" in captured.err


def test_a_missing_memory_folder_is_an_error(world, capsys):
    projects, memory = world
    Transcript(projects / "C--x-ScrapeX" / "s1.jsonl").call(T1, "Bash", {"command": "x"}, "y").save()
    assert _run(projects, memory.parent / "nowhere") == 1
    assert "no memory notes" in capsys.readouterr().err


def test_another_spelling_of_the_notes_path_still_counts_as_its_first_write(world, capsys):
    """Transcripts spell a path however the tool call did: on Windows with either
    separator and any case, elsewhere with `.` segments."""
    projects, memory = world
    note = _note(memory, "heredoc", HEREDOC)
    if sys.platform == "win32":
        spelling = str(note).replace("\\", "/").upper()
    else:
        spelling = f"{note.parent}/./{note.name}"
    Transcript(projects / "C--x-ScrapeX" / "s1.jsonl").call(T0, "Bash", {"command": "x"}, PARSE_ERROR) \
        .call(T1, "Edit", {"file_path": spelling}, "ok").call(T2, "Bash", {"command": "y"}, PARSE_ERROR).save()

    assert _run(projects, memory, "--json") == 0
    row = json.loads(capsys.readouterr().out)[0]
    assert (row["before"], row["after"]) == (1, 1), row


def test_a_scratch_copy_of_the_notes_is_dated_by_the_real_lesson(world, tmp_path, capsys):
    """Found by the calibration in #1104: a signature is tested on a COPY of the note,
    and dating by the scanned path put every recurrence in "before". The lesson began
    when the real note was first written, whichever copy is being scanned -- and a
    Write of the copy itself, outside the projects folder, is not that moment."""
    projects, memory = world
    real = _note(memory, "heredoc", HEREDOC)
    scratch = tmp_path / "scratch" / "memory"
    scratch.mkdir(parents=True)
    copy = _note(scratch, "heredoc", HEREDOC)
    Transcript(projects / "C--x-ScrapeX" / "s1.jsonl").call(T0, "Bash", {"command": "a"}, PARSE_ERROR) \
        .call(T1, "Write", {"file_path": str(real)}, "ok").call(T2, "Bash", {"command": "b"}, PARSE_ERROR) \
        .call(T3, "Write", {"file_path": str(copy)}, "ok").save()

    assert _run(projects, scratch, "--json") == 0
    row = json.loads(capsys.readouterr().out)[0]
    assert row["recorded"].startswith("2026-09-12") and (row["before"], row["after"]) == (1, 1)


def test_a_later_edit_of_the_note_does_not_move_when_the_lesson_began(world, capsys):
    """Notes get corrected: the heredoc lesson was rewritten nine days after it was
    first written. The failures between the two writes are recurrences, not history."""
    projects, memory = world
    note = _note(memory, "heredoc", HEREDOC)
    Transcript(projects / "C--x-ScrapeX" / "s1.jsonl").call(T1, "Write", {"file_path": str(note)}, "ok") \
        .call(T2, "Bash", {"command": "a"}, PARSE_ERROR).call(T3, "Edit", {"file_path": str(note)}, "ok").save()

    assert _run(projects, memory, "--json") == 0
    row = json.loads(capsys.readouterr().out)[0]
    assert row["recorded"].startswith("2026-09-12") and (row["before"], row["after"]) == (0, 1)


def test_a_write_of_a_copy_outside_the_projects_folder_never_dates_the_lesson(world, tmp_path, capsys):
    """An old lesson whose real first write is no longer in any transcript must fall
    back to its file's creation, not be dated by the day someone copied it to test a
    signature."""
    projects, memory = world
    _note(memory, "heredoc", HEREDOC)
    scratch = tmp_path / "scratch" / "memory"
    scratch.mkdir(parents=True)
    copy = _note(scratch, "heredoc", HEREDOC)
    Transcript(projects / "C--x-ScrapeX" / "s1.jsonl").call(T1, "Write", {"file_path": str(copy)}, "ok") \
        .call(T2, "Bash", {"command": "b"}, PARSE_ERROR).save()

    assert _run(projects, memory, "--json") == 0
    assert json.loads(capsys.readouterr().out)[0]["recorded_from"].startswith("file created")


def test_a_file_with_the_notes_name_outside_a_memory_folder_does_not_date_it(world, capsys):
    projects, memory = world
    _note(memory, "heredoc", HEREDOC)
    elsewhere = projects / "C--x-ScrapeX" / "notes" / "heredoc.md"
    Transcript(projects / "C--x-ScrapeX" / "s1.jsonl").call(T1, "Write", {"file_path": str(elsewhere)}, "ok") \
        .call(T2, "Bash", {"command": "b"}, PARSE_ERROR).save()

    assert _run(projects, memory, "--json") == 0
    assert json.loads(capsys.readouterr().out)[0]["recorded_from"].startswith("file created")


def test_a_call_the_transcript_records_twice_counts_once(world, capsys):
    """One session's transcript repeated its tool records (found by the calibration),
    which doubled its count."""
    projects, memory = world
    note = _note(memory, "heredoc", HEREDOC)
    t = Transcript(projects / "C--x-ScrapeX" / "s1.jsonl").call(T0, "Write", {"file_path": str(note)}, "ok") \
        .call(T1, "Bash", {"command": "a"}, PARSE_ERROR)
    t.lines.extend(t.lines[-2:])
    t.save()

    assert _run(projects, memory, "--json") == 0
    assert json.loads(capsys.readouterr().out)[0]["after"] == 1


def test_a_caveat_is_printed_beside_its_count(world, capsys):
    projects, memory = world
    note = _note(memory, "stale-main", "result: 'behind'\ncaveat: 'a floor: a merge left unpulled prints nothing'")
    Transcript(projects / "C--x-ScrapeX" / "s1.jsonl").call(T0, "Write", {"file_path": str(note)}, "ok") \
        .call(T1, "Bash", {"command": "git status"}, "behind by 2").save()

    assert _run(projects, memory) == 0
    lines = capsys.readouterr().out.splitlines()
    at = next(i for i, line in enumerate(lines) if line.startswith("stale-main"))
    assert lines[at + 1] == "    caveat: a floor: a merge left unpulled prints nothing"


@pytest.mark.parametrize(("checkout", "folder"), [
    # Both names are the folders Claude Code actually created on the development machine.
    (r"C:\Users\sapac\Desktop\Claude\ScrapeX", "C--Users-sapac-Desktop-Claude-ScrapeX"),
    (r"C:\Users\sapac\Desktop\Claude\ScrapeX\.claude\worktrees\one-skill-to-rule-them-all-1f850a",
     "C--Users-sapac-Desktop-Claude-ScrapeX--claude-worktrees-one-skill-to-rule-them-all-1f850a"),
])
def test_the_memory_folder_is_named_the_way_claude_code_names_it(checkout, folder):
    assert rs.project_folder(Path(checkout)) == folder
