"""How often a memory lesson broke again after it was written down is counted.

`tools/recurrence_scan.py` answers #1104 option 3: the counter a "second failure gets
a barrier" rule needs. A lesson's note never records its own recurrences, so the only
honest count comes from the session transcripts. These tests build a memory folder and
a projects folder of transcripts in the shapes Claude Code writes, and check every
branch that decides a number in the report.

THE TRANSCRIPT SHAPE IS THE REAL ONE, AND THAT IS THE POINT. Claude Code stores a tool
result as a plain string in 98.7% of real records (34,432 of 34,897 when this was
written), and as a list of parts in the rest. A fixture that wrote only lists let a
scanner that could not read strings pass every test while reporting zero for every
lesson on the real data. `Transcript.call` writes a string; one test writes a list.

WHY "RECORDED" IS THE CREATING WRITE AND NOTHING ELSE. The memory system moves
`modified` on every edit, and the Write tool replaces the file, which moves its
creation time too. Only the Write whose result says the file was created marks when
the lesson began; without it the start is unknown, and the report says so.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import recurrence_scan as rs  # noqa: E402

T0, T1, T2, T3 = ("2026-09-10T10:00:00.000Z", "2026-09-12T10:00:00.000Z",
                  "2026-09-14T10:00:00.000Z", "2026-09-16T10:00:00.000Z")
PARSE_ERROR = "Exit code 2\nbash: -c: line 3: unexpected EOF while looking for matching `''"
HEREDOC = "result: 'unexpected EOF while looking for matching'"


def _note(memory: Path, name: str, signature: str | None = None) -> Path:
    meta = "metadata:\n  type: feedback\n  modified: 2026-09-20T00:00:00.000Z\n"
    if signature is not None:
        meta += "  failure_signature:\n" + "".join(f"    {line}\n" for line in signature.splitlines())
    path = memory / f"{name}.md"
    path.write_text(f"---\nname: {name}\ndescription: d\n{meta}---\n\ntext\n", encoding="utf-8")
    return path


class Transcript:
    """One .jsonl file, written the way Claude Code writes a session."""

    def __init__(self, path: Path):
        self.path = path
        self.lines: list[str] = []
        self.n = 0

    def use(self, when: str, tool: str, given: dict) -> str:
        self.n += 1
        use_id = f"toolu_{self.path.stem}_{self.n}"
        self.lines.append(json.dumps({"type": "assistant", "timestamp": when, "message": {
            "role": "assistant", "content": [{"type": "tool_use", "id": use_id, "name": tool, "input": given}]}}))
        return use_id

    def result(self, when: str, use_id: str, text: str, *, as_list: bool = False) -> None:
        content = [{"type": "text", "text": text}] if as_list else text
        self.lines.append(json.dumps({"type": "user", "timestamp": when, "message": {
            "role": "user", "content": [{"type": "tool_result", "tool_use_id": use_id,
                                         "content": content, "is_error": text.startswith("Exit code")}]}}))

    def call(self, when: str, tool: str, given: dict, text: str, *, as_list: bool = False) -> Transcript:
        self.result(when, self.use(when, tool, given), text, as_list=as_list)
        return self

    def create(self, when: str, note: Path) -> Transcript:
        return self.call(when, "Write", {"file_path": str(note)}, f"File created successfully at: {note}")

    def update(self, when: str, note: Path) -> Transcript:
        return self.call(when, "Write", {"file_path": str(note)}, f"The file {note} has been updated successfully.")

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("\n".join(self.lines) + "\n", encoding="utf-8")


@pytest.fixture()
def world(tmp_path):
    projects = tmp_path / "projects"
    memory = projects / "C--x-ScrapeX" / "memory"
    memory.mkdir(parents=True)
    return projects, memory


def _session(projects: Path, name: str = "s1", folder: str = "C--x-ScrapeX") -> Transcript:
    return Transcript(projects / folder / f"{name}.jsonl")


def _run(projects: Path, memory: Path, *extra: str):
    return rs.main(["--projects", str(projects), "--memory", str(memory), *extra])


def _rows(capsys) -> dict:
    return {r["lesson"]: r for r in json.loads(capsys.readouterr().out)}


def test_a_failure_is_counted_before_and_after_the_creating_write(world, capsys):
    projects, memory = world
    note = _note(memory, "heredoc", HEREDOC)
    folder = "C--x-ScrapeX--claude-worktrees-a"
    _session(projects, "s1", folder).call(T0, "Bash", {"command": "python - <<'PY'"}, PARSE_ERROR) \
        .create(T1, note).save()
    # The latest failure sits in the file that is read FIRST, so "last" cannot be the
    # last call iterated.
    _session(projects, "s0", folder).call(T3, "Bash", {"command": "y"}, PARSE_ERROR) \
        .call(T3, "Bash", {"command": "z"}, "fine").save()
    _session(projects, "s2", folder).call(T2, "Bash", {"command": "x"}, PARSE_ERROR).save()

    assert _run(projects, memory, "--json") == 0
    row = _rows(capsys)["heredoc"]
    assert (row["before"], row["after"], row["total"], row["sessions_after"]) == (1, 2, 3, ["s0", "s2"])
    assert row["recorded"].startswith("2026-09-12") and row["recorded_from"] == "created in a transcript"
    assert row["last"].startswith("2026-09-16"), "the latest recurrence, whatever order the files are read in"


def test_a_result_stored_as_a_list_of_parts_is_read_too(world, capsys):
    projects, memory = world
    note = _note(memory, "heredoc", HEREDOC)
    _session(projects).create(T0, note).call(T1, "Bash", {"command": "a"}, PARSE_ERROR, as_list=True) \
        .call(T2, "Bash", {"command": "b"}, PARSE_ERROR).save()

    assert _run(projects, memory, "--json") == 0
    assert _rows(capsys)["heredoc"]["after"] == 2


@pytest.mark.parametrize("order", [
    (0, 1, 2),  # in order: the common case, 1,647 real results answered the OLDEST open call
    (2, 1, 0),  # newest first
    (1, 0, 2),  # a middle call answered first
])
def test_parallel_calls_are_each_paired_with_their_own_result(world, capsys, order):
    """Claude Code runs tool calls in parallel, so a result often arrives while other
    calls are open. Pairing by position (oldest or newest) instead of by id passes one
    of these orders and fails the others."""
    projects, memory = world
    note = _note(memory, "heredoc", HEREDOC)
    t = _session(projects).create(T0, note)
    commands = ["first", "second", "third"]
    outputs = [PARSE_ERROR, "fine", "also fine"]
    ids = [t.use(T1, "Bash", {"command": c}) for c in commands]
    for i in order:
        t.result(T1, ids[i], outputs[i])
    t.save()
    _note(memory, "second-only", "command: '^second$'\nresult: '^fine$'")
    _note(memory, "third-only", "command: '^third$'\nresult: '^also fine$'")

    assert _run(projects, memory, "--json") == 0
    totals = {name: r["total"] for name, r in _rows(capsys).items()}
    assert totals == {"heredoc": 1, "second-only": 1, "third-only": 1}


def test_two_failures_after_recording_flag_a_barrier_candidate_and_one_does_not(world, capsys):
    projects, memory = world
    twice = _note(memory, "twice", HEREDOC)
    once = _note(memory, "once", "result: 'no such thing'")
    _session(projects).create(T0, twice).create(T0, once) \
        .call(T1, "Bash", {"command": "a"}, PARSE_ERROR).call(T2, "Bash", {"command": "b"}, PARSE_ERROR) \
        .call(T2, "Bash", {"command": "c"}, "no such thing").save()

    assert _run(projects, memory) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[1].startswith("twice") and lines[1].endswith("barrier candidate"), "most recurrences first"
    assert lines[2].startswith("once") and "barrier" not in lines[2]


def test_a_shape_is_counted_and_never_flagged(world, capsys):
    """A shape is the form a lesson forbids, not evidence it broke: never a candidate."""
    projects, memory = world
    note = _note(memory, "piped", "command: '\\bpytest\\b[^|;&]*\\|\\s*tail'")
    t = _session(projects).create(T0, note)
    for when in (T1, T2, T3):
        t.call(when, "Bash", {"command": "pytest -q | tail -3"}, "5 passed")
    t.save()

    assert _run(projects, memory) == 0
    line = next(x for x in capsys.readouterr().out.splitlines() if x.startswith("piped"))
    assert " shape " in line and line.split()[4] == "3" and "barrier" not in line


def test_the_tool_filter_decides_which_calls_a_signature_reads(world, capsys):
    projects, memory = world
    notes = [_note(memory, "bash-only", "tool: Bash\nresult: 'boom'"),
             _note(memory, "shell", "result: 'boom'"),
             _note(memory, "listed", "tool: [PowerShell, Read]\nresult: 'boom'"),
             _note(memory, "any-tool", "tool: any\nresult: 'boom'")]
    t = _session(projects)
    for note in notes:
        t.create(T0, note)
    t.call(T1, "Bash", {"command": "a"}, "boom").call(T1, "PowerShell", {"command": "b"}, "boom") \
        .call(T1, "Read", {"file_path": "c"}, "boom").save()

    assert _run(projects, memory, "--json") == 0
    after = {name: r["after"] for name, r in _rows(capsys).items()}
    assert after == {"bash-only": 1, "shell": 2, "listed": 2, "any-tool": 3}


def test_a_tool_name_no_call_ever_used_is_reported_not_counted_as_zero(world, capsys):
    """`bash` for `Bash` would otherwise say "never broke again" -- the one answer this
    tool exists to stop giving without evidence."""
    projects, memory = world
    note = _note(memory, "lowercase", "tool: bash\nresult: 'boom'")
    _session(projects).create(T0, note).call(T1, "Bash", {"command": "a"}, "boom").save()

    assert _run(projects, memory) == 0
    out = capsys.readouterr().out
    assert "UNREADABLE SIGNATURE lowercase: tool bash matches none of the 2 calls" in out
    assert "case-sensitive" in out and "0 lessons measured" in out


def test_one_misspelt_name_in_a_list_is_reported_not_silently_dropped(world, capsys):
    """`[Bash, Powershell]` would otherwise count the Bash failures and quietly lose
    every PowerShell one."""
    projects, memory = world
    note = _note(memory, "listed", "tool: [Bash, Powershell]\nresult: 'boom'")
    _session(projects).create(T0, note).call(T1, "Bash", {"command": "a"}, "boom") \
        .call(T1, "PowerShell", {"command": "b"}, "boom").save()

    assert _run(projects, memory) == 0
    out = capsys.readouterr().out
    assert "UNREADABLE SIGNATURE listed: tool Powershell matches none of the 3 calls" in out


def test_shell_as_a_default_needs_no_powershell_call_to_be_valid(world, capsys):
    """`shell` is Bash and PowerShell; a machine that never ran PowerShell must not
    have every default signature reported as unusable."""
    projects, memory = world
    note = _note(memory, "heredoc", HEREDOC)
    _session(projects).create(T0, note).call(T1, "Bash", {"command": "a"}, PARSE_ERROR).save()

    assert _run(projects, memory, "--json") == 0
    row = _rows(capsys)["heredoc"]
    assert (row["error"], row["after"]) == (None, 1)


@pytest.mark.parametrize("folder", [
    ("parent", "subagents", "workflows", "wf_1"),  # a workflow agent
    ("parent", "subagents"),                         # an Agent-tool subagent
])
def test_a_subagent_transcript_counts_for_the_session_that_ran_it(world, capsys, folder):
    projects, memory = world
    note = _note(memory, "heredoc", HEREDOC)
    base = projects / "C--x-ScrapeX"
    Transcript(base / "parent.jsonl").create(T0, note).save()
    Transcript(base.joinpath(*folder, "agent-a.jsonl")).call(T1, "Bash", {"command": "x"}, PARSE_ERROR).save()

    assert _run(projects, memory, "--json") == 0
    assert _rows(capsys)["heredoc"]["sessions_after"] == ["parent"]


def test_only_this_projects_transcripts_are_read(world, capsys):
    projects, memory = world
    note = _note(memory, "heredoc", HEREDOC)
    _session(projects).create(T0, note).save()
    _session(projects, "s2", "C--x-other-project").call(T1, "Bash", {"command": "x"}, PARSE_ERROR).save()
    Transcript(projects / "C--x-ScrapeX" / "s1" / "journal.jsonl").call(T1, "Bash", {"command": "x"}, PARSE_ERROR).save()

    assert _run(projects, memory, "--json") == 0
    assert _rows(capsys)["heredoc"]["total"] == 0


def test_a_later_edit_of_the_note_does_not_move_when_the_lesson_began(world, capsys):
    """Notes get corrected: the heredoc lesson was rewritten nine days after it was
    first written. The failures between the two writes are recurrences, not history."""
    projects, memory = world
    note = _note(memory, "heredoc", HEREDOC)
    _session(projects).create(T1, note).call(T2, "Bash", {"command": "a"}, PARSE_ERROR) \
        .call(T3, "Edit", {"file_path": str(note)}, "ok").update(T3, note).save()

    assert _run(projects, memory, "--json") == 0
    row = _rows(capsys)["heredoc"]
    assert row["recorded"].startswith("2026-09-12") and (row["before"], row["after"]) == (0, 1)


def test_a_note_created_again_after_a_deletion_keeps_its_first_creation(world, capsys):
    """A consolidation pass can delete a note and write it afresh; the lesson still
    began at its first creation."""
    projects, memory = world
    note = _note(memory, "heredoc", HEREDOC)
    _session(projects).create(T1, note).call(T2, "Bash", {"command": "a"}, PARSE_ERROR).create(T3, note).save()

    assert _run(projects, memory, "--json") == 0
    row = _rows(capsys)["heredoc"]
    assert row["recorded"].startswith("2026-09-12") and (row["before"], row["after"]) == (0, 1)


@pytest.mark.parametrize(("writes", "reason"), [
    ("none", "no write of the note survives in any transcript"),
    ("update only", "the earliest surviving write is an update, so the lesson is older"),
])
def test_without_the_creating_write_the_start_is_unknown_and_nothing_is_flagged(world, capsys, writes, reason):
    """The file's own creation time is no substitute: the Write tool replaces the file,
    so it equals the LAST write, which is the defect `metadata.modified` has too."""
    projects, memory = world
    note = _note(memory, "old-lesson", HEREDOC)
    t = _session(projects)
    if writes == "update only":
        t.update(T0, note)
    t.call(T1, "Bash", {"command": "a"}, PARSE_ERROR).call(T2, "Bash", {"command": "b"}, PARSE_ERROR).save()

    assert _run(projects, memory) == 0
    out = capsys.readouterr().out
    line = next(x for x in out.splitlines() if x.startswith("old-lesson"))
    assert line.split()[2:7] == ["unknown", "?", "?", "2", "0"] and "barrier" not in line
    assert f"START UNKNOWN old-lesson: {reason}" in out

    assert _run(projects, memory, "--json") == 0
    row = _rows(capsys)["old-lesson"]
    assert (row["recorded"], row["before"], row["after"], row["total"], row["sessions_after"]) == \
        (None, None, None, 2, []), "a script must not read an unknown start as 'never broke again'"


@pytest.mark.parametrize("update_first", [False, True])
def test_a_recognised_update_never_masks_an_unrecognised_create(world, capsys, update_first):
    """The common shape: a note is created, then edited (7 of the 23 real notes). If a
    release rewords only the create message, the edit's familiar wording must not make
    the report claim "an update" and bury the unreadable create beside it."""
    projects, memory = world
    note = _note(memory, "heredoc", HEREDOC)
    unread = _session(projects, "a" if update_first else "z").call(
        T0, "Write", {"file_path": str(note)}, "Wrote a new file")
    unread.call(T1, "Bash", {"command": "a"}, PARSE_ERROR).save()
    _session(projects, "z" if update_first else "a").call(
        T2, "Edit", {"file_path": str(note)}, f"The file {note} has been updated successfully.").save()

    assert _run(projects, memory) == 0
    reason = next(x for x in capsys.readouterr().out.splitlines() if x.startswith("START UNKNOWN heredoc"))
    assert "does not recognise" in reason and "an update" not in reason


def test_a_write_result_in_neither_known_wording_is_named_not_taken_for_an_update(world, capsys):
    """If a Claude Code release rewords the Write tool's result, every lesson would lose
    its date. The reason must say the scanner could not read the result, not claim an
    update it never saw."""
    projects, memory = world
    note = _note(memory, "heredoc", HEREDOC)
    _session(projects).call(T0, "Write", {"file_path": str(note)}, "Wrote a new file") \
        .call(T1, "Bash", {"command": "a"}, PARSE_ERROR).save()

    assert _run(projects, memory) == 0
    out = capsys.readouterr().out
    assert "START UNKNOWN heredoc: a write of the note printed a result this scanner does not recognise" in out
    assert "'Wrote a new file'" in out and "update" not in out.split("START UNKNOWN heredoc")[1].split("\n")[0]


def test_a_scratch_copy_of_the_notes_is_dated_by_the_real_lesson(world, tmp_path, capsys):
    """Found by the calibration in #1104: a signature is tested on a COPY of the note,
    and dating by the scanned path put every recurrence in "before"."""
    projects, memory = world
    real = _note(memory, "heredoc", HEREDOC)
    scratch = tmp_path / "scratch" / "memory"
    scratch.mkdir(parents=True)
    copy = _note(scratch, "heredoc", HEREDOC)
    _session(projects).call(T0, "Bash", {"command": "a"}, PARSE_ERROR).create(T1, real) \
        .call(T2, "Bash", {"command": "b"}, PARSE_ERROR).create(T3, copy).save()

    assert _run(projects, scratch, "--json") == 0
    row = _rows(capsys)["heredoc"]
    assert row["recorded"].startswith("2026-09-12") and (row["before"], row["after"]) == (1, 1)


def test_a_copy_created_outside_the_projects_folder_never_dates_the_lesson(world, tmp_path, capsys):
    projects, memory = world
    _note(memory, "heredoc", HEREDOC)
    scratch = tmp_path / "scratch" / "memory"
    scratch.mkdir(parents=True)
    copy = _note(scratch, "heredoc", HEREDOC)
    _session(projects).create(T1, copy).call(T2, "Bash", {"command": "b"}, PARSE_ERROR).save()

    assert _run(projects, memory, "--json") == 0
    assert _rows(capsys)["heredoc"]["recorded"] is None


def test_a_file_with_the_notes_name_outside_a_memory_folder_does_not_date_it(world, capsys):
    projects, memory = world
    _note(memory, "heredoc", HEREDOC)
    elsewhere = projects / "C--x-ScrapeX" / "notes" / "heredoc.md"
    _session(projects).create(T1, elsewhere).call(T2, "Bash", {"command": "b"}, PARSE_ERROR).save()

    assert _run(projects, memory, "--json") == 0
    assert _rows(capsys)["heredoc"]["recorded"] is None


def test_another_spelling_of_the_notes_path_still_counts_as_its_creating_write(world, capsys):
    """Transcripts spell a path however the tool call did: on Windows with either
    separator and any case, elsewhere with `.` segments."""
    projects, memory = world
    note = _note(memory, "heredoc", HEREDOC)
    spelling = str(note).replace("\\", "/").upper() if sys.platform == "win32" else f"{note.parent}/./{note.name}"
    _session(projects).call(T0, "Bash", {"command": "x"}, PARSE_ERROR) \
        .call(T1, "Write", {"file_path": spelling}, f"File created successfully at: {spelling}") \
        .call(T2, "Bash", {"command": "y"}, PARSE_ERROR).save()

    assert _run(projects, memory, "--json") == 0
    row = _rows(capsys)["heredoc"]
    assert (row["before"], row["after"]) == (1, 1), row


def test_a_call_the_transcript_records_twice_counts_once(world, capsys):
    """One session's transcript repeated its tool records (found by the calibration),
    which doubled its count."""
    projects, memory = world
    note = _note(memory, "heredoc", HEREDOC)
    t = _session(projects).create(T0, note).call(T1, "Bash", {"command": "a"}, PARSE_ERROR)
    t.lines.extend(t.lines[-2:])
    t.save()

    assert _run(projects, memory, "--json") == 0
    assert _rows(capsys)["heredoc"]["after"] == 1


def test_a_caveat_is_printed_beside_its_count_and_in_the_json(world, capsys):
    projects, memory = world
    note = _note(memory, "stale-main", "result: 'behind'\ncaveat: 'a floor: a merge left unpulled prints nothing'")
    _session(projects).create(T0, note).call(T1, "Bash", {"command": "git status"}, "behind by 2").save()

    assert _run(projects, memory) == 0
    lines = capsys.readouterr().out.splitlines()
    at = next(i for i, line in enumerate(lines) if line.startswith("stale-main"))
    assert lines[at + 1] == "    caveat: a floor: a merge left unpulled prints nothing"
    assert _run(projects, memory, "--json") == 0
    row = _rows(capsys)["stale-main"]
    assert (row["kind"], row["caveat"], row["error"]) == ("failure", "a floor: a merge left unpulled prints nothing", None)


@pytest.mark.parametrize(("signature", "said"), [
    ("result: '(unclosed'", "result is not a valid regex"),
    ("kind: failure\ncommand: 'x'", "a failure signature needs a result pattern"),
    ("tool: Bash", "needs a command or a result pattern"),
    ("result: 'x'\nwhen: always", "unknown keys"),
    ("kind: sometimes\nresult: 'x'", "kind must be failure or shape"),
    ("result: ''", "result is not a non-empty string"),
    ("result: 5", "result is not a non-empty string"),
    ("result: 'x'\ncaveat: 3", "caveat is not a string"),
    ("tool: [Bash, 5]\nresult: 'x'", "tool must be a tool name or a list of them"),
    ("tool: null\nresult: 'x'", "tool must be a tool name or a list of them"),
    ("tool: []\nresult: 'x'", "tool must be a tool name or a list of them"),
    ("tool: [shell, Read]\nresult: 'x'", "shell and any stand alone"),
])
def test_an_unreadable_signature_is_reported_by_name_and_the_rest_still_scan(world, capsys, signature, said):
    projects, memory = world
    _note(memory, "broken", signature)
    good = _note(memory, "good", HEREDOC)
    _session(projects).create(T0, good).call(T1, "Bash", {"command": "x"}, PARSE_ERROR).save()

    assert _run(projects, memory) == 0
    out = capsys.readouterr().out
    assert "UNREADABLE SIGNATURE broken: " in out and said in out
    assert any(line.startswith("good") and line.split()[4] == "1" for line in out.splitlines())
    assert "0 with no failure_signature" in out, "a broken signature is not an unmeasured lesson"


@pytest.mark.parametrize(("text", "said"), [
    ("---\nname: flat\nmetadata:\n  failure_signature: 'just a string'\n---\n\nx\n",
     "failure_signature is not a mapping"),
    ("---\nname: flat\nmetadata: 'just a string'\n---\n\nx\n", "metadata is not a mapping"),
    ("\ufeff---\nname: flat\nmetadata:\n  type: feedback\n---\n\nx\n", "no frontmatter"),
    ("no frontmatter at all\n", "no frontmatter"),
    # A real note on this machine (another project) has exactly this: an unquoted ': '.
    ("---\nname: flat\ndescription: a lesson: with a colon\n---\n\nx\n", "mapping values are not allowed here"),
])
def test_a_note_whose_frontmatter_cannot_be_read_is_reported_by_name(world, capsys, text, said):
    """The byte-order mark case is a lesson in its own right on this machine: PowerShell
    5.1 writes one, and a SKILL.md with it silently stops loading."""
    projects, memory = world
    (memory / "flat.md").write_text(text, encoding="utf-8")
    _session(projects).call(T1, "Bash", {"command": "x"}, "y").save()
    assert _run(projects, memory) == 0
    assert f"UNREADABLE SIGNATURE flat: {said}" in capsys.readouterr().out


def test_notes_without_a_signature_are_named_as_unmeasured_and_the_index_is_skipped(world, capsys):
    projects, memory = world
    _note(memory, "semantic-lesson")
    (memory / "MEMORY.md").write_text("- index\n", encoding="utf-8")
    _session(projects).call(T1, "Bash", {"command": "x"}, "y").save()

    assert _run(projects, memory) == 0
    out = capsys.readouterr().out
    assert "0 lessons measured, 1 with no failure_signature: semantic-lesson" in out
    assert "MEMORY" not in out


@pytest.mark.parametrize("setup", ["no transcripts", "no tool calls", "no projects folder"])
def test_an_empty_scan_is_an_error_about_the_scanner_not_a_clean_report(world, capsys, setup):
    """"Nothing recurred" and "I read nothing" must never print the same thing."""
    projects, memory = world
    _note(memory, "heredoc", HEREDOC)
    if setup == "no tool calls":
        path = projects / "C--x-ScrapeX" / "s1.jsonl"
        path.write_text(json.dumps({"type": "user", "message": {"content": "hello"}}) + "\n", encoding="utf-8")
    target = projects / "missing" if setup == "no projects folder" else projects

    assert rs.main(["--projects", str(target), "--memory", str(memory)]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "not evidence that nothing recurred" in captured.err


def test_a_missing_memory_folder_is_an_error(world, capsys):
    projects, memory = world
    _session(projects).call(T1, "Bash", {"command": "x"}, "y").save()
    assert _run(projects, memory.parent / "nowhere") == 1
    assert "no memory notes" in capsys.readouterr().err


def test_a_relative_projects_path_dates_lessons_like_an_absolute_one(world, capsys, monkeypatch):
    """A relative --projects never matched a Write's absolute path, which silently sent
    every lesson to an unknown start."""
    projects, memory = world
    note = _note(memory, "heredoc", HEREDOC)
    _session(projects).create(T0, note).call(T1, "Bash", {"command": "a"}, PARSE_ERROR).save()
    monkeypatch.chdir(projects.parent)

    assert rs.main(["--projects", projects.name, "--memory", str(memory), "--json"]) == 0
    assert _rows(capsys)["heredoc"]["recorded_from"] == "created in a transcript"


@pytest.mark.parametrize(("checkout", "folder"), [
    # Both names are the folders Claude Code actually created on the development machine.
    (r"C:\Users\sapac\Desktop\Claude\ScrapeX", "C--Users-sapac-Desktop-Claude-ScrapeX"),
    (r"C:\Users\sapac\Desktop\Claude\ScrapeX\.claude\worktrees\one-skill-to-rule-them-all-1f850a",
     "C--Users-sapac-Desktop-Claude-ScrapeX--claude-worktrees-one-skill-to-rule-them-all-1f850a"),
])
def test_the_memory_folder_is_named_the_way_claude_code_names_it(checkout, folder):
    assert rs.project_folder(Path(checkout)) == folder


# THE WEEKLY LOG. `--markdown` writes one comment for the log issue, and hides a copy of
# the run at its end; `--previous` reads the last such copy back, so each comment says
# what changed since the one before. A number compared across two different signatures
# compares two different measures, which is what the fingerprint refuses.


def _markdown(projects: Path, memory: Path, capsys, previous: Path | None = None) -> str:
    extra = ("--previous", str(previous)) if previous else ()
    assert _run(projects, memory, "--markdown", *extra) == 0
    return capsys.readouterr().out


def _table(text: str) -> dict[str, list[str]]:
    """lesson -> its cells, from the comment's table."""
    rows = [line.strip("|").split(" | ") for line in text.splitlines() if line.startswith("| `")]
    return {cells[0].strip(" `"): [c.strip() for c in cells[1:]] for cells in rows}


def _new_candidates(text: str) -> str:
    return next(x for x in text.splitlines() if x.startswith("**New barrier candidates**")).split(": ", 1)[1]


def test_the_first_comment_is_the_table_and_a_hidden_copy_of_the_run(world, capsys):
    projects, memory = world
    twice = _note(memory, "twice", HEREDOC)
    once = _note(memory, "once", "result: 'no such thing'\ncaveat: 'a floor: this one is shy'")
    shape = _note(memory, "piped", "command: 'pytest.*\\| tail'")
    older = _note(memory, "older", HEREDOC)
    _note(memory, "unsigned")
    _session(projects).create(T0, twice).create(T0, once).create(T0, shape).update(T0, older) \
        .call(T1, "Bash", {"command": "a"}, PARSE_ERROR).call(T2, "Bash", {"command": "b"}, PARSE_ERROR) \
        .call(T2, "Bash", {"command": "c"}, "no such thing") \
        .call(T2, "Bash", {"command": "pytest | tail"}, "ok").call(T3, "Bash", {"command": "pytest | tail"}, "ok") \
        .call(T3, "Bash", {"command": "pytest -x | tail"}, "ok").save()

    text = _markdown(projects, memory, capsys)
    assert "The log's first run." in text and text.startswith("## Recurrence scan, ")
    table = _table(text)
    assert list(table) == ["piped", "twice", "once", "older"], "most recurrences first, as in the report"
    #                          kind      recorded      before after since        total sessions last          flag
    assert table["twice"] == ["failure", "2026-09-10", "0", "2", "first run", "2", "1", "2026-09-14", "**barrier candidate**"]
    assert table["piped"][:2] == ["shape", "2026-09-10"] and table["piped"][3] == "3" and table["piped"][-1] == ""
    assert table["once"][3] == "1" and table["once"][-1] == ""
    assert table["older"] == ["failure", "unknown", "?", "?", "first run", "2", "?", "-", ""], \
        "an unknown start shows no split, no sessions and no flag"
    assert _new_candidates(text) == "`twice`"
    assert "- caveat on `once`: a floor: this one is shy" in text
    assert "- start unknown for `older`: `the earliest surviving write is an update, so the lesson is older`" in text
    assert "4 lessons measured, 1 with no failure_signature: `unsigned`" in text

    assert text.rstrip().splitlines()[-1].startswith(rs.MARK), "the copy closes the comment"
    run, lessons = rs.load_previous(text)
    assert run == rs.dt.date.today().isoformat()
    assert set(lessons) == {"twice", "piped", "once", "older"}, "an unsigned note has no count to compare"
    assert (lessons["twice"]["after"], lessons["twice"]["candidate"]) == (2, True)
    assert (lessons["older"]["after"], lessons["older"]["candidate"]) == (None, False)
    assert lessons["twice"]["fingerprint"] == rs.fingerprint(rs.parse_signature(
        {"result": "unexpected EOF while looking for matching"}))


def test_the_next_comment_says_what_changed_since_the_last(world, capsys, tmp_path):
    projects, memory = world
    grows = _note(memory, "grows", HEREDOC)
    flagged = _note(memory, "flagged", "result: 'boom'")
    becomes = _note(memory, "becomes", "result: 'bang'")
    rewritten = _note(memory, "rewritten", "result: 'crash'")
    gone = _note(memory, "gone", "result: 'fizz'")
    older = _note(memory, "older", "result: 'fizz'")
    first = _session(projects, "s1").create(T0, grows).create(T0, flagged).create(T0, becomes) \
        .create(T0, rewritten).create(T0, gone).update(T0, older) \
        .call(T1, "Bash", {"command": "a"}, PARSE_ERROR).call(T1, "Bash", {"command": "a2"}, PARSE_ERROR) \
        .call(T1, "Bash", {"command": "b"}, "boom").call(T1, "Bash", {"command": "c"}, "boom") \
        .call(T1, "Bash", {"command": "d"}, "bang").call(T1, "Bash", {"command": "e"}, "crash")
    first.save()
    previous = tmp_path / "prev.md"
    previous.write_text(_markdown(projects, memory, capsys), encoding="utf-8")

    _session(projects, "s2").call(T2, "Bash", {"command": "f"}, PARSE_ERROR) \
        .call(T2, "Bash", {"command": "g"}, "bang").call(T2, "Bash", {"command": "h"}, "boom") \
        .call(T2, "Bash", {"command": "i"}, "fizz").save()
    gone.unlink()
    _note(memory, "rewritten", "result: 'crash|burn'")
    newcomer = _note(memory, "newcomer", "result: 'boom'")
    _session(projects, "s3").create(T3, newcomer).save()

    text = _markdown(projects, memory, capsys, previous)
    assert f"Compared with the run of {rs.load_previous(previous.read_text(encoding='utf-8'))[0]}." in text
    since = {name: cells[4] for name, cells in _table(text).items()}
    assert _table(text)["grows"][3] == "3"
    assert since == {"grows": "+1", "flagged": "+1", "becomes": "+1", "rewritten": "signature changed",
                     "older": "?", "newcomer": "new lesson"}
    assert _new_candidates(text) == "`becomes`", "a lesson flagged last week is not new; one flagged now is"
    assert "**Signature changed** since the last run, so its count starts a new baseline: `rewritten`" in text
    assert "**No longer measured** since the last run: `gone`" in text


def test_the_last_run_in_the_file_is_the_baseline_and_an_unchanged_world_changes_nothing(world, capsys, tmp_path):
    """The log's comments are fetched in order into one file, so the LAST copy in it is
    last week's run; an earlier one with other numbers must not be read."""
    projects, memory = world
    note = _note(memory, "twice", HEREDOC)
    _session(projects).create(T0, note).call(T1, "Bash", {"command": "a"}, PARSE_ERROR) \
        .call(T2, "Bash", {"command": "b"}, PARSE_ERROR).save()
    latest = _markdown(projects, memory, capsys)
    stale = latest.replace('"after":2,"candidate":true', '"after":0,"candidate":false')
    assert stale != latest
    previous = tmp_path / "prev.md"
    previous.write_text(stale + "\nsomeone replied in between\n" + latest, encoding="utf-8")

    text = _markdown(projects, memory, capsys, previous)
    assert _table(text)["twice"][4] == "+0"
    assert _new_candidates(text) == "none."
    assert "**Signature changed**" not in text and "**No longer measured**" not in text


@pytest.mark.parametrize(("then", "now_known"), [
    (1, False),  # the creating Write was in a transcript that is gone now
    (None, True),  # last week could not date it; this week can
])
def test_a_count_is_compared_only_when_both_runs_knew_the_start(world, capsys, tmp_path, then, now_known):
    projects, memory = world
    note = _note(memory, "lesson", HEREDOC)
    t = _session(projects)
    if now_known:
        t.create(T0, note)
    t.call(T1, "Bash", {"command": "a"}, PARSE_ERROR).save()
    copy = {"run": "2026-09-21", "lessons": [{"lesson": "lesson", "after": then, "candidate": False,
                                              "fingerprint": rs.fingerprint(rs.parse_signature({"result": "unexpected EOF while looking for matching"}))}]}
    previous = tmp_path / "prev.md"
    previous.write_text(rs.MARK + json.dumps(copy) + " -->\n", encoding="utf-8")

    assert _table(_markdown(projects, memory, capsys, previous))["lesson"][4] == "?"


@pytest.mark.parametrize(("change", "same"), [
    ({"kind": "failure"}, True),  # the default written out is the same measure
    ({"caveat": "read the session"}, True),  # a caveat changes how to read, not what is counted
    ({"tool": ["Bash", "PowerShell"]}, True),  # what `shell` means, written as a list
    ({"result": "unexpected EOF"}, False),
    ({"tool": "Bash"}, False),
    ({"command": "python"}, False),
])
def test_the_fingerprint_changes_with_what_is_counted_and_nothing_else(change, same):
    base = {"result": "unexpected EOF while looking for matching"}
    before = rs.fingerprint(rs.parse_signature(base))
    assert (rs.fingerprint(rs.parse_signature({**base, **change})) == before) is same
    assert (rs.fingerprint(rs.parse_signature({"result": "x", "kind": "shape"}))
            != rs.fingerprint(rs.parse_signature({"result": "x"})))


def test_no_lesson_name_can_close_the_hidden_copy_or_break_the_table():
    """A lesson is a file name, and on Linux a file name may hold `-->` or `|`."""
    sig = rs.parse_signature({"result": "x"})
    row = rs.Row(rs.Note("a|b-->c", Path("a.md"), sig), rs.dt.datetime(2026, 9, 10), "created in a transcript")
    row.after, row.total = 2, 2
    text = rs.markdown([row], rs.dt.datetime(2026, 9, 28), 1, 3)

    copy = text.splitlines()[-1]
    assert copy.count("-->") == 1 and copy.endswith(" -->"), "only the copy's own end closes the comment"
    assert "| `a\\|b-->c` |" in text, "the pipe is escaped, so the row keeps its cells"
    assert list(rs.load_previous(text)[1]) == ["a|b-->c"]


def test_a_quoted_tool_result_can_neither_mention_a_user_nor_link_an_issue(world, capsys):
    """The reason for an unknown start quotes a tool's output, and a GitHub comment
    would ping `@name` and link `#12` written outside a code span."""
    projects, memory = world
    note = _note(memory, "heredoc", HEREDOC)
    _session(projects).call(T0, "Write", {"file_path": str(note)}, "Wrote `it for @octocat, see #12") \
        .call(T1, "Bash", {"command": "a"}, PARSE_ERROR).save()

    text = _markdown(projects, memory, capsys)
    line = next(x for x in text.splitlines() if x.startswith("- start unknown for `heredoc`"))
    assert "@octocat" in line
    outside = "".join(line.split("`")[0::2])
    assert "@octocat" not in outside and "#12" not in outside


def test_previous_needs_markdown_and_markdown_excludes_json(world, tmp_path):
    projects, memory = world
    with pytest.raises(SystemExit) as exc:
        _run(projects, memory, "--previous", str(tmp_path / "prev.md"))
    assert exc.value.code == 2
    with pytest.raises(SystemExit) as exc:
        _run(projects, memory, "--markdown", "--json")
    assert exc.value.code == 2


@pytest.mark.parametrize(("content", "said"), [
    ("## a comment written by hand\n", "carries no recurrence-scan block"),
    ('<!-- recurrence-scan {"run":"2026-09-21","lessons":[]}\n', "is not closed"),
    ("<!-- recurrence-scan {not json} -->", "is not JSON"),
    ("<!-- recurrence-scan [] -->", "is not a run of lessons"),
    ('<!-- recurrence-scan {"run":"2026-09-21","lessons":[{"lesson":"a"}]} -->', "is not a run of lessons"),
    ('<!-- recurrence-scan {"run":"2026-09-21","lessons":[{"lesson":"a","fingerprint":"f",'
     '"after":"2","candidate":false}]} -->', "is not a run of lessons"),
    ('<!-- recurrence-scan {"run":"2026-09-21","lessons":[{"lesson":"a","fingerprint":"f",'
     '"after":true,"candidate":false}]} -->', "is not a run of lessons"),
    ('<!-- recurrence-scan {"run":"2026-09-21","lessons":[{"lesson":"a","fingerprint":"f",'
     '"after":1}]} -->', "is not a run of lessons"),
    ('<!-- recurrence-scan {"run":"2026-09-21","lessons":[{"lesson":"a",'
     '"after":1,"candidate":false}]} -->', "is not a run of lessons"),
    ('<!-- recurrence-scan {"lessons":[]} -->', "is not a run of lessons"),
    (None, "cannot compare with"),
])
def test_a_previous_run_that_cannot_be_read_is_an_error_not_a_first_run(world, capsys, tmp_path, content, said):
    """Read as "no previous run", every lesson would be reported new and every
    candidate would be owed a second issue."""
    projects, memory = world
    note = _note(memory, "heredoc", HEREDOC)
    _session(projects).create(T0, note).call(T1, "Bash", {"command": "a"}, PARSE_ERROR).save()
    previous = tmp_path / "prev.md"
    if content is not None:
        previous.write_text(content, encoding="utf-8")

    assert _run(projects, memory, "--markdown", "--previous", str(previous)) == 1
    captured = capsys.readouterr()
    assert captured.out == "", "no half-compared comment"
    assert "cannot compare with" in captured.err and said in captured.err


@pytest.mark.parametrize("output", [(), ("--markdown",)])
def test_a_caveat_outside_the_windows_code_page_survives_a_redirected_run(world, output):
    """Redirected on Windows, stdout encodes cp1252, and one caveat outside it killed
    the whole report; the log's comment is always a redirected run."""
    projects, memory = world
    note = _note(memory, "arrow", "result: 'boom'\ncaveat: 'a floor → اقرأ الجلسة'")
    _session(projects).create(T0, note).call(T1, "Bash", {"command": "a"}, "boom").save()
    env = {**os.environ, "PYTHONIOENCODING": "cp1252"}
    env.pop("PYTHONUTF8", None)

    done = subprocess.run([sys.executable, str(ROOT / "tools" / "recurrence_scan.py"), "--projects", str(projects),
                           "--memory", str(memory), *output], capture_output=True, env=env, check=False)
    assert done.returncode == 0, done.stderr.decode("utf-8", "replace")
    assert "a floor → اقرأ الجلسة" in done.stdout.decode("utf-8")


def test_an_error_naming_a_path_outside_the_windows_code_page_is_printed_not_a_crash(world, tmp_path):
    """The errors go to stderr, which encodes cp1252 as well when redirected, and they
    name paths the owner chose."""
    projects, memory = world
    _note(memory, "heredoc", HEREDOC)
    _session(projects).create(T0, memory / "heredoc.md").save()
    missing = tmp_path / "سجل الأسبوع.md"
    env = {**os.environ, "PYTHONIOENCODING": "cp1252"}
    env.pop("PYTHONUTF8", None)

    done = subprocess.run([sys.executable, str(ROOT / "tools" / "recurrence_scan.py"), "--projects", str(projects),
                           "--memory", str(memory), "--markdown", "--previous", str(missing)],
                          capture_output=True, env=env, check=False)
    err = done.stderr.decode("utf-8")
    assert done.returncode == 1 and "Traceback" not in err
    assert "cannot compare with" in err and "سجل الأسبوع.md" in err
