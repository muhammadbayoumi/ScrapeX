"""A remap must be applied ONCE, and content-equality cannot tell you that it was.

WHAT HAPPENED, MEASURED. Six lines added to `extension/app.js` slid every citation below
them. Ten rows were repaired by re-deriving each from the finished tree. A second, wider
pass then remapped every `app.js` citation across `docs/` -- and remapped those ten A
SECOND TIME: `848 -> 853` became `848 -> 853 -> 861`.

WHY THE CHECK IN PLACE PASSED AT BOTH HOPS. Every rewrite was verified as
`origin/main[old] == finished[new]`. The shift is uniform, so the content at line 853 of
the old file equals the content at line 861 of the new one just as truly as it did one
hop earlier. **Content-equality proves a mapping is consistent; it cannot prove it was
applied once.**

The stronger claim needs a different KIND of check, not a stricter version of the same
one -- the same mistake as reading `s.count(old) == 1` as proof of LOCATION.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

#: MARKED BECAUSE THE DETECTOR IS DELIBERATELY BROAD, AND NOT BECAUSE THIS FILE READS
#: THE EXTENSION. `test_the_extension_gate_is_complete` matches any file naming
#: `extension/`, and says why in terms: *"a false positive costs one marker, a false
#: negative costs a guard nobody notices is gone."* This file names
#: `extension/app.js` in its own history and in its fixtures -- the remap that went
#: twice was over that file's citations -- so it trips the pattern honestly. Rewording
#: the fixtures to dodge a guard whose broadness is its design would be optimising
#: against the guard instead of paying its stated price.
pytestmark = pytest.mark.extension

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import verify_citation_remap as tool  # noqa: E402


def _write(folder: Path, relative: str, text: str) -> Path:
    path = folder / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_a_double_application_is_caught(tmp_path):
    """THE DEFECT ITSELF. The mapping says one hop; the document shows two."""
    was = tmp_path / "was"
    now = tmp_path / "now"
    _write(was, "docs/a.md", "See `extension/app.js` at extension/app.js:848 for why.\n")
    _write(now, "docs/a.md", "See `extension/app.js` at extension/app.js:861 for why.\n")

    complaints = tool.verify(str(was), now, "docs/a.md",
                             {("extension/app.js", "848"): "853"})

    assert complaints, "a double application was not caught"
    assert "applied more than once" in complaints[0], complaints
    assert "848" in complaints[0] and "861" in complaints[0] and "853" in complaints[0]


def test_one_hop_passes(tmp_path):
    """The tool has to accept the correct repair, or nobody will run it."""
    was, now = tmp_path / "was", tmp_path / "now"
    _write(was, "docs/a.md", "at extension/app.js:848 and scrapex/jobs.py:12\n")
    _write(now, "docs/a.md", "at extension/app.js:853 and scrapex/jobs.py:12\n")

    assert tool.verify(str(was), now, "docs/a.md",
                       {("extension/app.js", "848"): "853"}) == []


def test_a_move_nobody_asked_for_is_caught(tmp_path):
    """A citation that changed while the mapping says nothing about it was moved by
    something other than this remap -- which is worth knowing before it is believed."""
    was, now = tmp_path / "was", tmp_path / "now"
    _write(was, "docs/a.md", "at scrapex/jobs.py:12\n")
    _write(now, "docs/a.md", "at scrapex/jobs.py:99\n")

    complaints = tool.verify(str(was), now, "docs/a.md", {})

    assert complaints and "does not mention it" in complaints[0], complaints


def test_a_changed_citation_count_refuses_to_pair(tmp_path):
    """A remap changes NUMBERS and never how many citations there are. Pairing over a
    different edit would line up citations that have nothing to do with each other and
    report confident nonsense."""
    was, now = tmp_path / "was", tmp_path / "now"
    _write(was, "docs/a.md", "at scrapex/jobs.py:12\n")
    _write(now, "docs/a.md", "at scrapex/jobs.py:12 and scrapex/db.py:7\n")

    complaints = tool.verify(str(was), now, "docs/a.md", {})

    assert complaints and "never how many citations" in complaints[0], complaints


def test_a_fence_is_blanked_to_equal_line_count(tmp_path):
    """STRIPPING A FENCE SHIFTS EVERY LINE AFTER IT, so it is blanked and never removed.
    Paid for in one afternoon by two different sessions."""
    text = "one\n```\nscrapex/jobs.py:5\n```\ntwo scrapex/db.py:9\n"

    blanked = tool.blank_fences(text)

    assert len(blanked.splitlines()) == len(text.splitlines()), (
        "the fence changed the line count, so every position after it is now wrong")
    assert tool.citations(text) == [("scrapex/db.py", "9")], (
        "a citation inside a fence was counted, or the real one was lost")


def test_a_backtick_span_crossing_a_newline_does_not_split(tmp_path):
    """AN INLINE SPAN CAN CROSS A NEWLINE. A single-line matcher sees two spans where
    there are none and reads the text between them as prose."""
    text = ("A `span that\ncrosses a line` and then scrapex/jobs.py:31 in prose.\n")

    found = tool.citations(text)

    assert found == [("scrapex/jobs.py", "31")], found
    assert len(tool.strip_inline_code(text).splitlines()) == len(text.splitlines())


def test_a_citation_inside_backticks_is_not_prose(tmp_path):
    """A citation shown as inline code is an EXAMPLE, and remapping an example rewrites
    what the document was demonstrating."""
    assert tool.citations("see `scrapex/jobs.py:5` for the shape\n") == []


def test_a_snapshot_is_refused_outright(tmp_path):
    """ELEVEN REFERENCES INSIDE THESE TWO WERE REWRITTEN AND HAD TO BE RESTORED. Their
    headers pin them to a commit, so rewriting a reference inside one makes the snapshot
    say something it did not say -- and a previous session had already made and reverted
    exactly that mistake."""
    assert tool.SNAPSHOTS, "the refusal list is empty, so nothing is protected"
    for relative in tool.SNAPSHOTS:
        assert (ROOT / relative).is_file(), (
            f"{relative} is named as a snapshot and does not exist -- a refusal list "
            "naming a missing file protects nothing")
        complaints = tool.verify("HEAD", ROOT, relative, {})
        assert complaints and "must not be remapped" in complaints[0], complaints


def test_the_citation_pattern_is_the_guards_own(tmp_path):
    """TWO PATTERNS WOULD BE TWO DEFINITIONS OF WHAT A CITATION IS, and the day they
    disagree this tool blesses a document the guard rejects."""
    from tests import test_the_documents_cite_what_they_claim as guard

    assert tool.CITATION.pattern == guard.CITATION.pattern, (
        "the tool and the guard no longer agree on what a citation looks like")
    assert tool.SUFFIXES == guard.SUFFIXES


def test_the_mapping_refuses_a_shape_it_cannot_mean(tmp_path):
    """A mapping entry is `old:new` digits. Anything else is a typo that would otherwise
    silently match nothing and report a clean run."""
    assert tool.parse_mapping("extension/app.js=848:853") == {
        ("extension/app.js", "848"): "853"}
    assert tool.parse_mapping("a.js=1:2,3:4; b.py=5:6") == {
        ("a.js", "1"): "2", ("a.js", "3"): "4", ("b.py", "5"): "6"}

    for broken in ("extension/app.js", "a.js=848", "a.js=eight:853", "a.js=848:x"):
        with pytest.raises(SystemExit):
            tool.parse_mapping(broken)


def test_it_runs_over_the_real_documents_and_reports_a_count(capsys):
    """A TOOL NOBODY CAN RUN IS A TOOL NOBODY RUNS. `--was HEAD` against the working
    tree is the no-op case, and it must pass and say how much it looked at."""
    exit_code = tool.main(["--was", "HEAD", "--mapping", "extension/app.js=1:1"])

    said = capsys.readouterr().out
    assert exit_code == 0, said
    assert "paired and checked" in said
    counted = int(said.split("paired and checked ")[1].split(" ")[0])
    assert counted > 0, (
        "it paired zero citations across the real documents, so a clean verdict from it "
        "would mean nothing")
