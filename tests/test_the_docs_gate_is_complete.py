"""The set of tests that guard the documents must not shrink by accident.

The sibling of tests/test_the_extension_gate_is_complete.py, and it exists for
the same reason at a different seam. CI runs `pytest -m docs` when a change
touches only documentation, so a Markdown edit stops dragging a 2,656-test engine
suite behind it. The whole value of that depends on one thing: the marked set
really being every test that reads a document.

MEASURED when the tier was made, 2026-08-19: nine files under tests/ read a
documentation file, carrying 178 tests that run in 30.6 seconds -- against 451
seconds for the whole suite locally and 12m49s in CI. The largest by far is the
privacy policy suite; the citation guard reads the eight documents in CLAUDE.md's
map.

WHY IT IS NOT ENOUGH TO REUSE THE EXTENSION MARK, and this was found rather than
assumed. `tests/test_the_ruling_matches_the_code.py` reads
`docs/data-page-schema.md` and asserts it equals what the generator produces. It
carries no extension mark and never needed one -- it touches no extension file.
But `docs/` was already inside the old extension-only path filter, so a
documentation-only change ran `pytest -m extension` and DID NOT RUN IT. A
hand-edited `docs/data-page-schema.md` would have passed CI on the very kind of
pull request that hand-edits it. The two sets overlap and neither contains the
other, which is why the extension tier now runs `-m "extension or docs"`.

THE FAILURE THIS PREVENTS IS THE ONE THAT HAS HAPPENED TWICE HERE. The panel
suite reported green for months while 48 tests skipped silently. The document
guards are newer and more fragile in exactly the same way: write a test that reads
CLAUDE.md, forget the mark, and it stops running on the pull requests it was
written for. Nothing goes red. Nothing looks different.
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

#: A file "reads a document" if it names one in a STRING, or joins a `docs` path
#: segment. Deliberately broad in the same way READS_EXTENSION next door is: a
#: false positive costs one marker, a false negative costs a guard nobody notices
#: is gone.
#:
#: IT STARTED NARROWER AND THE NARROW VERSION MISSED THE MOST IMPORTANT FILE.
#: The first pattern required a `/` before the quoted name -- `ROOT / "docs" /
#: "data-page-schema.md"` -- and so did not see
#: tests/test_the_documents_cite_what_they_claim.py, which holds its eight
#: documents in a plain tuple of names and resolves them later. That is the
#: citation guard: the one test whose entire subject is the documents. A guard
#: whose detector cannot see the most important member of the set is not a guard,
#: and matching any quoted `*.md` is what fixes it.
READS_A_DOCUMENT = re.compile(
    r'''"[\w.\-/]*\.md"'''
    r'''|(?:ROOT|parents\[1\]|parent\.parent)\s*/\s*"docs"''')

#: The floor, not the count -- same reasoning as LEAST_TESTS_IN_THE_GATE next
#: door. 178 tests carried the mark when the tier was made. It is CHECKED because
#: without it the set can be emptied one file at a time while CI keeps reporting
#: a green docs gate over nothing.
LEAST_TESTS_IN_THE_GATE = 150


def _test_files() -> list[pathlib.Path]:
    return sorted((ROOT / "tests").glob("test_*.py"))


def test_every_test_file_that_reads_a_document_carries_the_mark():
    """THE GUARD. Without it the docs tier is a promise rather than a mechanism."""
    unmarked = []
    for path in _test_files():
        source = path.read_text(encoding="utf-8")
        if not READS_A_DOCUMENT.search(source):
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


def test_the_mark_is_declared_so_a_typo_cannot_be_silent():
    """`--strict-markers` turns `pytest.mark.dcos` into an error.

    Without it an unknown mark is a warning, the file quietly leaves the set, and
    the gate keeps passing -- the same shape of failure as the one above, reached
    by a different route. Asserted here as well as next door because either
    marker could be removed from `pyproject.toml` on its own.
    """
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    # `addopts`, not the whole file -- the same trap the extension gate records
    # hitting on its first attempt, and this file walked into it too. The flag is
    # NAMED in the comment beside the marker declarations, so a plain substring
    # search finds its own explanation and passes with the flag switched off.
    # Confirmed by mutation: removing it from addopts left the old assertion green.
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
    would not notice 178 tests becoming 3 -- which is precisely how the panel
    suite went quiet."""
    marked = [path for path in _test_files() if carries(path, "docs")]

    assert len(marked) >= 8, (
        f"only {len(marked)} test files carry the docs mark; nine did when the "
        "tier was built. A file leaves this set when its READS go, never to "
        "quiet a failure.")

    # `def test_` at the start of a line, which is how every test in this
    # repository is written. Parametrised cases multiply this, so the real
    # collected count is higher -- the safe direction for a floor. Same
    # arithmetic as the extension gate next door, and the same slack.
    functions = sum(
        len(re.findall(r"^def test_", path.read_text(encoding="utf-8"), re.MULTILINE))
        for path in marked)
    assert functions >= LEAST_TESTS_IN_THE_GATE - 60, (
        f"the docs gate is down to {functions} test functions; 178 collected "
        "tests were measured when the tier was made")


def test_the_workflow_actually_runs_the_docs_tier():
    """A marked set nothing runs is worse than no set: it reads as coverage.

    The extension gate has the same exposure and no test for it, so this asserts
    for both -- if a future edit deletes either tier from the workflow while
    leaving the markers behind, this is what says so."""
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    # THE WHOLE `run:` LINE, not the substring. `pytest -m docs` also appears in
    # the --collect-only floor step a few lines above, so the substring version
    # passed with the step that actually RUNS the tier deleted. Confirmed by
    # mutation before this line was written.
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
#: change and may run 178 tests instead of 2,656".
CLASSIFICATION = (
    ("docs/STATE.md", True),
    ("docs/plans/2026-08-16-muqawil-contractor-source.md", True),
    ("CLAUDE.md", True),
    ("CHANGELOG.md", True),
    (".gitignore", True),
    (".claude/skills/karpathy-guidelines/SKILL.md", True),
    # THE DANGEROUS DIRECTION. Every one of these must run the whole suite; a
    # pattern that admits any of them turns a code change into a 30-second
    # documentation run and says nothing.
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
    `scrapex/` to it by accident and a change to the warehouse runs 178
    documentation tests and reports green. This lifts the pattern out of ci.yml
    and classifies real paths with it, so the rule is tested rather than trusted.
    """
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    # THE POLARITY, BEFORE THE PATTERN. `! grep -qvE` means "no changed line
    # FAILS to match", i.e. all of them match. Plain `grep -qE` means "at least
    # one matches" -- the opposite -- and would classify a diff of one Markdown
    # file plus one connector as documentation. Extracting the regex alone cannot
    # see that: an adversarial pass inverted these two lines and every assertion
    # in this file stayed green, so the lines are pinned verbatim.
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
    # like a documentation change. Reproduced before this was pinned.
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
    # cases below are the ones the two dialects agree on.
    pattern = re.compile(found.group(1))

    wrong = [(path, expected) for path, expected in CLASSIFICATION
             if bool(pattern.search(path)) is not expected]

    assert not wrong, "\n".join(
        ["the documentation pattern classifies these wrongly:"]
        + [f"  {path!r} -> {'documentation' if not want else 'NOT documentation'}, "
           f"expected {'documentation' if want else 'NOT documentation'}"
           for path, want in wrong])
