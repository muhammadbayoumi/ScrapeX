"""The set of tests that guard the documents must not shrink by accident.

The sibling of tests/test_the_extension_gate_is_complete.py, and it exists for
the same reason at a different seam. CI runs `pytest -m docs` when a change
touches only documentation, so a Markdown edit stops dragging the whole engine
suite behind it. The whole value of that depends on one thing: the marked set
really being every test that reads a document.

RESTORED BY #651. #467 deleted this file along with the documents it retired, and
CI kept routing on the mark with nothing left to keep the mark honest. The miss
that proved it was already there when it came back: tests/test_ui_kit.py reads
docs/UI-KIT.md and carried only `extension`, so a documentation-only change to
that file did not run the one test that checks it.

WHY IT IS NOT ENOUGH TO REUSE THE EXTENSION MARK, and this was found rather than
assumed. `tests/test_the_ruling_matches_the_code.py` reads
`docs/data-page-schema.md` and asserts it equals what the generator produces. It
carries no extension mark and never needed one -- it touches no extension file.
But `docs/` was once inside an extension-only path filter, so a documentation-only
change ran `pytest -m extension` and DID NOT RUN IT. The two sets overlap and
neither contains the other, which is why the extension tier runs
`-m "extension or docs"`.

THE FAILURE THIS PREVENTS IS THE ONE THAT HAS HAPPENED HERE BEFORE. The panel suite
reported green for months while 48 tests skipped silently. The document guards are
fragile in exactly the same way: write a test that reads a document, forget the
mark, and it stops running on the pull requests it was written for. Nothing goes
red. Nothing looks different.
"""

from __future__ import annotations

import pathlib
import re

import pytest

from tests.marks import carries

# BOTH marks. This file reads a document, and its CLASSIFICATION table below names
# `extension/app.js`, which is what the extension gate's own detector looks for --
# so it belongs to both sets and says so rather than being admitted by accident.
pytestmark = [pytest.mark.extension, pytest.mark.docs]

ROOT = pathlib.Path(__file__).resolve().parents[1]

#: A quoted name ending `.md`, or a path joined onto a `docs` segment.
QUOTED_MARKDOWN = re.compile(r'''"([\w.\-/]*\.md)"''')
JOINS_DOCS = re.compile(r'''(?:ROOT|parents\[1\]|parent\.parent)\s*/\s*"docs"''')


def _documents() -> set[str]:
    """Every Markdown file in the documentation set, as a repo path and a bare name.

    The set is the one ci.yml's `documentation=` pattern routes on: the root's own
    `*.md`, and everything under docs/ and .claude/. A bare name is included
    because this suite joins paths -- `ROOT / "docs" / "UI-KIT.md"` quotes only
    the last segment.
    """
    found = [*ROOT.glob("*.md"), *(ROOT / "docs").rglob("*.md"),
             *(ROOT / ".claude").rglob("*.md")]
    names: set[str] = set()
    for path in found:
        names.add(path.relative_to(ROOT).as_posix())
        names.add(path.name)
    return names


def reads_a_document(source: str, documents: set[str]) -> bool:
    """Whether this test source reads a file in the documentation set.

    A quoted `*.md` name counts ONLY IF IT NAMES A REAL DOCUMENT. The detector this
    file had before #467 counted any quoted `.md`, and on today's tree that flags
    tests that WRITE Markdown into `tmp_path` -- `"docs/a.md"`, `"MEMORY.md"`, a
    scratch notes file -- which read nothing a documentation change could alter.
    Marking them would run them on every docs-only change for no reason, and a
    list of exemptions would rot the first time one was renamed. Asking the tree
    is exact and needs no upkeep.

    IT STARTED NARROWER BEFORE, AND THAT MISSED THE MOST IMPORTANT FILE: a first
    pattern required a `/` before the quoted name, so it did not see the citation
    guard, which holds its documents in a plain tuple of names. Matching every
    quoted name and then checking it exists keeps that fixed.

    WHAT IT STILL CANNOT SEE, named rather than implied: a file in the set that is
    not Markdown and is named as a bare string -- `docs/picker/scrapex-picker.html`
    joined as `ROOT / page` -- and `.gitignore`. ci.yml routes both to the docs
    tier. tests/test_the_markup_we_ship_closes_its_own_tags.py marks itself for
    exactly that reason and says so beside its mark.
    """
    if JOINS_DOCS.search(source):
        return True
    return any(name in documents for name in QUOTED_MARKDOWN.findall(source))


#: The floor, not the count -- same reasoning as LEAST_TESTS_IN_THE_GATE next
#: door. It is CHECKED because without it the set can be emptied one file at a
#: time while CI keeps reporting a green docs gate over nothing.
LEAST_TESTS_IN_THE_GATE = 150


def _test_files() -> list[pathlib.Path]:
    return sorted((ROOT / "tests").glob("test_*.py"))


def test_every_test_file_that_reads_a_document_carries_the_mark():
    """THE GUARD. Without it the docs tier is a promise rather than a mechanism."""
    documents = _documents()
    assert documents, "found no Markdown in the documentation set; the reader is broken"

    unmarked = []
    for path in _test_files():
        source = path.read_text(encoding="utf-8")
        if not reads_a_document(source, documents):
            continue
        # `carries`, not `in source`. A substring search counts this very file as
        # marked on the strength of the line above and the message below -- see
        # tests/marks.py, where that was measured.
        if not carries(path, "docs"):
            unmarked.append(path.name)

    assert not unmarked, (
        "these test files read a documentation file and would stop running on a "
        "documentation-only change:\n  " + "\n  ".join(unmarked) + "\n\nAdd "
        "`pytest.mark.docs` to the file's pytestmark. A file that guards both a "
        "document and the extension carries both marks:\n"
        "    pytestmark = [pytest.mark.extension, pytest.mark.docs]")


def test_the_reader_tells_a_document_from_a_scratch_file():
    """The exactness above is a claim, so it is pinned both ways."""
    documents = _documents()
    assert reads_a_document('(ROOT / "docs" / "UI-KIT.md").read_text()', documents)
    assert reads_a_document('DOCUMENTS = ("CLAUDE.md", "README.md")', documents)
    assert not reads_a_document('(tmp_path / "MEMORY.md").write_text("x")', documents)
    assert not reads_a_document('_write(was, "docs/a.md", "x")', documents)


def test_the_mark_is_declared_so_a_typo_cannot_be_silent():
    """`--strict-markers` turns `pytest.mark.dcos` into an error.

    Without it an unknown mark is a warning, the file quietly leaves the set, and
    the gate keeps passing -- the same shape of failure as the one above, reached
    by a different route. Asserted here as well as next door because either
    marker could be removed from `pyproject.toml` on its own.
    """
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    # `addopts`, not the whole file. The flag is NAMED in the comment beside the
    # marker declarations, so a plain substring search finds its own explanation
    # and passes with the flag switched off.
    addopts = re.search(r'^addopts = "([^"]*)"', pyproject, re.MULTILINE)
    assert addopts, "pyproject.toml no longer sets addopts"
    assert "--strict-markers" in addopts.group(1), (
        "--strict-markers is gone from addopts; a misspelled mark is now a "
        "warning and a file can leave the docs set without failing anything")
    assert re.search(r'^\s*"docs:', pyproject, re.MULTILINE), (
        "the `docs` marker is not registered in pyproject.toml, so "
        "--strict-markers will reject every file that carries it")


def test_the_gate_still_collects_a_real_suite():
    """The count, not just the presence of a mark. A per-file 'at least one'
    would not notice a hundred tests becoming three -- which is precisely how the
    panel suite went quiet."""
    marked = [path for path in _test_files() if carries(path, "docs")]

    assert len(marked) >= 8, (
        f"only {len(marked)} test files carry the docs mark. A file leaves this "
        "set when its READS go, never to quiet a failure.")

    # `def test_` at the start of a line, which is how every test in this
    # repository is written. Parametrised cases multiply this, so the real
    # collected count is higher -- the safe direction for a floor.
    functions = sum(
        len(re.findall(r"^def test_", path.read_text(encoding="utf-8"), re.MULTILINE))
        for path in marked)
    assert functions >= LEAST_TESTS_IN_THE_GATE - 60, (
        f"the docs gate is down to {functions} test functions")


def test_the_workflow_actually_runs_the_docs_tier():
    """A marked set nothing runs is worse than no set: it reads as coverage."""
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    # THE WHOLE `run:` LINE, not the substring. `pytest -m docs` also appears in
    # the --collect-only floor step, so the substring version passed with the
    # step that actually RUNS the tier deleted.
    assert "run: python -m pytest -m docs\n" in workflow, (
        "ci.yml has no step whose whole command is `python -m pytest -m docs`, so "
        "the docs mark selects a suite that never executes. The --collect-only "
        "gate step does not count: it collects and never runs.")
    assert 'scope=docs' in workflow, (
        "ci.yml no longer computes a `docs` scope, so the tier can never be "
        "chosen no matter what carries the mark")
    assert 'pytest -m "extension or docs"' in workflow, (
        "the extension tier stopped including the docs set. "
        "tests/test_the_ruling_matches_the_code.py carries no extension mark, so "
        "an extension+docs change would stop checking docs/data-page-schema.md")


#: What the workflow's `documentation=` pattern must and must not admit. The left
#: column is a changed-file path; True means "this alone is a documentation-only
#: change and may run the docs tier instead of the whole suite".
CLASSIFICATION = (
    ("docs/STATE.md", True),
    ("docs/archive/RULINGS.md", True),
    ("CLAUDE.md", True),
    ("CHANGELOG.md", True),
    (".gitignore", True),
    (".claude/skills/review/SKILL.md", True),
    # THE DANGEROUS DIRECTION. Every one of these must run the whole suite; a
    # pattern that admits any of them turns a code change into a documentation
    # run and says nothing.
    ("scrapex/features.py", False),
    ("scrapex/webui/templates/settings.html", False),
    ("extension/app.js", False),
    ("tests/test_vendor.py", False),
    ("sources.yaml", False),
    ("pyproject.toml", False),
    # A workflow edit changes what CI itself guarantees -- including an edit to
    # the very pattern this test reads.
    (".github/workflows/ci.yml", False),
    # docs/ is a prefix of nothing else, but a pattern written without the
    # anchor would match this and quietly exempt a connector.
    ("scrapex/connectors/docs/reader.py", False),
)


def test_the_workflows_documentation_pattern_admits_exactly_what_it_should():
    """The scope rule is a bash regex inside YAML, which no linter reads.

    A widened pattern is silent and expensive in the dangerous direction: add
    `scrapex/` to it by accident and a change to the warehouse runs the
    documentation tests and reports green. This lifts the pattern out of ci.yml
    and classifies real paths with it, so the rule is tested rather than trusted.
    """
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    # THE POLARITY, BEFORE THE PATTERN. `! grep -qvE` means "no changed line
    # FAILS to match", i.e. all of them match. Plain `grep -qE` means "at least
    # one matches" -- the opposite -- and would classify a diff of one Markdown
    # file plus one connector as documentation. Extracting the regex alone cannot
    # see that: an adversarial pass inverted these two lines and every other
    # assertion stayed green, so the lines are pinned verbatim.
    for decision in (
            'if ! echo "$changed" | grep -qvE "$documentation"; then',
            'elif ! echo "$changed" | grep -qvE "^(extension/)|$documentation"; then'):
        assert decision in workflow, (
            f"the scope decision no longer reads {decision!r}. If the shape "
            "changed, re-derive the polarity and update this list -- a `grep -qE` "
            "where a `! grep -qvE` was means ANY file matching is enough, and a "
            "code change would run the documentation tier.")

    # And the diff must stay rename-blind: `--name-only` alone reports only a
    # move's destination, so a file moved out of scrapex/ into docs/ would look
    # like a documentation change.
    assert 'git diff --name-only --no-renames' in workflow, (
        "the scope diff lost --no-renames, so a file MOVED into docs/ or "
        "extension/ reports only its destination and the engine suite is skipped "
        "on a change that deleted an engine file")

    found = re.search(r"^\s*documentation='([^']+)'", workflow, re.MULTILINE)
    assert found, (
        "ci.yml no longer defines a `documentation=` pattern in the scope job, so "
        "this test cannot check what the docs tier admits. If the rule moved, move "
        "this test with it -- do not delete it.")

    # ERE from the shell; Python's `re` is close enough for these paths, and the
    # cases above are the ones the two dialects agree on.
    pattern = re.compile(found.group(1))

    wrong = [(path, expected) for path, expected in CLASSIFICATION
             if bool(pattern.search(path)) is not expected]

    assert not wrong, "\n".join(
        ["the documentation pattern classifies these wrongly:"]
        + [f"  {path!r} -> {'documentation' if not want else 'NOT documentation'}, "
           f"expected {'documentation' if want else 'NOT documentation'}"
           for path, want in wrong])
