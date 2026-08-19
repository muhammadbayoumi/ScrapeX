"""The set of tests that guard the extension must not shrink by accident.

CI runs `pytest -m extension` when a change touches only `extension/`, so that
a button change stops dragging the 2020-test engine suite behind it. The whole
value of that depends on one thing: the marked set really being every test that
guards the extension.

MEASURED when the split was made: eleven files under tests/ read `extension/`
sources — 325 of 2020 tests. The largest are the panel DOM suite (112), the
vendored-asset gates (58), the native host (32) and the version ledger (32).

THE FAILURE THIS PREVENTS IS SILENT AND HAS HAPPENED HERE BEFORE. The panel
suite opened with `pytest.importorskip("playwright")` and reported green for
months in CI while 48 behavioural tests — including the panel's only XSS guard
— skipped without a word. A split is the second way to get exactly that: write
a new test file that reads `extension/`, forget the mark, and it simply stops
running on the pull requests it was written for. Nothing goes red. Nothing
looks different.

WHY THE SPLIT IS ASYMMETRIC, and why there is no `-m "not extension"` anywhere.
Two of the eleven guard the ENGINE as well — `test_version.py` covers the
engine's own ledger, `test_native.py` covers the native messaging host — so
excluding the marked set from the engine run would drop them on engine changes.
An extension-only change runs the marked subset; everything else runs the whole
suite, exactly as before. Neither direction loses a test.
"""

from __future__ import annotations

import pathlib
import re

import pytest

from tests.marks import carries

pytestmark = pytest.mark.extension

ROOT = pathlib.Path(__file__).resolve().parents[1]

#: A file "reads the extension" if it names the directory in any of the forms
#: this repository uses. Deliberately broad: a false positive costs one marker,
#: a false negative costs a guard nobody notices is gone.
READS_EXTENSION = re.compile(r'"extension"|\bextension/')

#: The floor, not the count. It is a floor because tests are added constantly
#: and an equality would fail on every one of them; it is CHECKED because
#: without it the marked set can be emptied one file at a time while CI keeps
#: reporting a green extension gate over nothing.
LEAST_TESTS_IN_THE_GATE = 300


def _test_files() -> list[pathlib.Path]:
    return sorted((ROOT / "tests").glob("test_*.py"))


def test_every_test_file_that_reads_the_extension_carries_the_mark():
    """THE GUARD. Without it the split is a promise rather than a mechanism."""
    unmarked = []
    for path in _test_files():
        source = path.read_text(encoding="utf-8")
        if not READS_EXTENSION.search(source):
            continue
        # `carries`, not `in source`: THIS FILE mentions the mark four times in
        # its own prose and messages, so the substring version reported it as
        # marked whether it was or not. Measured 2026-08-19 -- see tests/marks.py.
        if not carries(path, "extension"):
            unmarked.append(path.name)

    assert not unmarked, (
        "these test files read extension/ sources and would stop running on an "
        "extension-only change:\n  " + "\n  ".join(unmarked) + "\n\nAdd "
        "`pytestmark = pytest.mark.extension` after the imports.")


def test_the_mark_is_declared_so_a_typo_cannot_be_silent():
    """`--strict-markers` turns `pytest.mark.extenson` into an error.

    Without it an unknown mark is a warning, the file quietly leaves the set,
    and the gate keeps passing — the same shape of failure as the one above,
    arrived at by a different route.
    """
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    # `addopts`, not the file: the flag is named in the comment beside the
    # marker declaration, so a plain substring search finds its own explanation
    # and passes with the flag switched off — measured, on the first attempt.
    addopts = re.search(r'^addopts = "([^"]*)"', pyproject, re.MULTILINE)
    assert addopts, "pyproject.toml no longer sets addopts"
    assert "--strict-markers" in addopts.group(1), (
        "an unknown marker is only a warning again, so a misspelt "
        "`pytest.mark.extension` silently removes a file from the gate")
    assert re.search(r'^\s*"extension:', pyproject, re.MULTILINE), (
        "the extension marker is no longer declared in pyproject.toml")


def test_the_gate_still_holds_enough_tests_to_be_a_gate(pytestconfig):
    """A floor, because a gate that collects nothing passes fastest of all.

    Counted by reading the marks rather than by running pytest inside pytest:
    the number that matters is how many tests CARRY the mark, and that is a
    fact about the files.
    """
    marked_files = [p for p in _test_files() if carries(p, "extension")]
    assert len(marked_files) >= 10, (
        f"only {len(marked_files)} files are in the extension gate; eleven were "
        "measured when the split was made")

    # `def test_` at the start of a line, which is how every test in this
    # repository is written. Parametrised cases multiply this, so the real
    # collected count is higher — which is the safe direction for a floor.
    functions = sum(
        len(re.findall(r"^def test_", p.read_text(encoding="utf-8"), re.MULTILINE))
        for p in marked_files)
    assert functions >= LEAST_TESTS_IN_THE_GATE - 60, (
        f"the extension gate is down to {functions} test functions; it was "
        f"measured at 325 collected tests when the split was made")
