"""A test named in a comment has to be a test somebody can open.

WHY THIS EXISTS. The documents are guarded -- `R-15`, and
`tests/test_the_documents_cite_what_they_claim.py` checks every `file:line` in
`CLAUDE.md`, `ENGINEERING.md` and `docs/`. Test files are guarded by nothing, and
they carry the same kind of claim: a docstring that says *"this is why, see
`test_foo`"* is a citation, and it rots the same way.

FOUND ON 2026-08-22, three references, all to one deleted test, and THE DATES ARE
THE ARGUMENT. `test_the_engine_overflow_trigger_has_no_visible_resting_container`
was added by `8796fb5` on 2026-08-10 and removed by `ce80886` on 2026-08-20, when
the Engine page's overflow menu was replaced by action rows and the trigger it
measured stopped existing. A ten-day-old test had accumulated three dangling
citations within two days of dying. This is not slow rot that a careful reader
would eventually notice -- it is the default outcome of deleting a test anything
else explains itself by. Two comments in `tests/test_panel_dom.py` went on naming
it as though a reader could open it:

  * `settle_view`'s docstring -- the whole evidentiary basis for a helper still
    used four times. Every number in it (20/20 reads mid-animation, 7/20 outright
    failures, height 47.99999237060547 = 48 - 2**-17) was measured against that
    test. A reader who doubted the wait had nothing to re-measure against, and
    that docstring's own first line is *"a wait with no visible cause is a wait
    the next reader deletes"*.
  * `test_the_back_button_out_of_one_engine_is_a_borderless_pill` -- cited it for
    the technique of reading the CSSOM as well as the box.

Neither comment was WRONG about the facts. The `button, .button { min-height:
var(--control-height) }` clamp is real and still in `design/components.css`, and
the 47.5 incident happened. What had gone was the ability to CHECK either, which
is the only thing a citation is for.

WHY AN ALLOWLIST RATHER THAN A PATTERN. The obvious version greps the surrounding
prose for "renamed from" or "no longer exists" and forgives those. That was
written first and thrown away: it decides whether a reference is honest by
keyword, so it passes any dead name that happens to sit near the word "removed"
and fails an honest one phrased differently. This repository already settled this
shape twice -- `PINNED` in the guard next door, and `RESERVED` in
`test_the_registers_cannot_collide.py`. **A deliberate exception is DECLARED, not
inferred.** So a historical name is written down here with where to read it, and
anything else must be a test that exists.
"""
from __future__ import annotations

import collections
import pathlib
import re

import pytest

# NO `pytestmark`, DELIBERATELY AND NOT BY OMISSION. This file reads `tests/` and
# nothing else -- not the browser side's sources, not a document -- so it belongs
# to neither tier and runs in the full suite, which is where it has to run: test
# docstrings change on every kind of pull request, not on one tier's.
#
# AND THAT IS WHY THE PROSE HERE DOES NOT SPELL THE BROWSER DIRECTORY'S NAME.
# `test_the_extension_gate_is_complete` matches that name in any file under
# `tests/` and then demands the matching marker, which would move this file into
# the tier CI runs SEPARATELY -- so it would stop running on an engine-only or
# docs-only change. The gate's own note says a false positive "costs one marker";
# here the marker would cost the guard. The same trade, for the same reason, is
# already taken in `tests/test_the_version_moves_when_the_contract_does.py`, whose
# prose avoids the name for exactly this. Caught by that gate on the first run of
# this file, which is the gate working.
#
# (An empty `pytestmark = ()` is not the way to say "no marks": pytest unpacks it
# and fails collection with `got () instead of Mark`. Say it in prose, as here.)

ROOT = pathlib.Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"

#: A backticked test name in prose. Six characters past the prefix keeps `test_x`
#: placeholders in example snippets out of it, and the backticks keep ordinary
#: prose about "the test_foo family" out too -- only a name someone deliberately
#: marked up as code is treated as a reference.
REFERENCE = re.compile(r"`(test_[A-Za-z0-9_]{6,})`")

#: TESTS THAT NO LONGER EXIST AND ARE NAMED ON PURPOSE, with where to read them.
#: A row here is a promise that `git show <ref>:<path>` still produces the test,
#: which is what makes naming it useful rather than decorative -- and it is
#: checked below rather than trusted.
#:
#: Delete a row when the last reference to it goes. Add one only when the history
#: is the point; if a test was renamed and the new name says the same thing, cite
#: the new name instead and add nothing here.
HISTORICAL = {
    "test_health_accepts_a_legacy_v1_scrapex_warehouse_for_migration": (
        "f221abc3", "tests/test_storage.py",
        "renamed 2026-09-03 to test_health_refuses_a_warehouse_older_than_the_"
        "baseline_and_says_why, because `R-84` retires the promise it recorded for "
        "the period before publication and restores it after: a warehouse below the "
        "squashed baseline has no upgrade path, so `health()` reporting it as "
        "upgradable was the thing that had to change. Its old body had also stopped "
        "testing its own name -- it built a database by executing SCHEMA_FILE, which "
        "was v1 while the baseline declared 1 and is the HEAD now"),
    "test_the_engine_overflow_trigger_has_no_visible_resting_container": (
        "8796fb5", "tests/test_panel_dom.py",
        "added by 8796fb5 (#151), removed by ce80886 (#217) with the Engine "
        "page's overflow menu; settle_view's measurements were taken against it"),
    "test_the_legacy_marker_is_the_migrations_own_and_not_a_copy": (
        "8901a2a", "tests/test_a_carry_over_upgrades_rather_than_starting_over.py",
        "removed 2026-08-29 with `db/migrations/0058_a_unit_that_can_name_who_said_it.sql`, "
        "the file it read: it compared the carry-over's legacy marker against the "
        "migration's own text, and the migration went with the stream his ruling retired. "
        "The six carry-over tests around it are untouched -- the function they guard is "
        "still shipped"),
    "test_frozen_entry_defaults_to_the_native_host": (
        "ff21042", "tests/test_native.py",
        "renamed to test_an_unknown_argument_is_chrome_rather_than_cli_usage by "
        "7a067c5 (#141), when no-arguments stopped meaning the native host and "
        "started meaning first-run setup"),
}

#: A guard that can be emptied without anyone noticing is the defect -- SR-23 and
#: OP-18, the same reason `PINNED_FLOOR` exists next door. This floor is below
#: today's count on purpose.
REFERENCE_FLOOR = 20


def _test_files() -> list[pathlib.Path]:
    return sorted(TESTS.glob("test_*.py"))


def _defined() -> dict[str, set[str]]:
    """Test function name -> the files defining it."""
    found: dict[str, set[str]] = collections.defaultdict(set)
    for path in _test_files():
        for match in re.finditer(r"^def (test_[A-Za-z0-9_]+)",
                                 path.read_text(encoding="utf-8"), re.M):
            found[match.group(1)].add(path.name)
    return found


def _references():
    for path in _test_files():
        text = path.read_text(encoding="utf-8")
        for match in re.finditer(REFERENCE, text):
            line = text.count("\n", 0, match.start()) + 1
            yield path.name, line, match.group(1)


def test_every_test_named_in_a_comment_exists_or_is_declared_historical():
    """THE GUARD. A name that is neither a live test, a gate module, nor a
    declared historical row sends its reader looking for nothing."""
    defined = _defined()
    modules = {path.stem for path in _test_files()}
    dangling = [
        f"{where}:{line} names `{name}`"
        for where, line, name in _references()
        if name not in defined and name not in modules and name not in HISTORICAL
    ]

    assert not dangling, "\n  ".join([
        "these comments name a test that does not exist. Either cite the test "
        "that replaced it, or add a row to HISTORICAL saying where to read the "
        "one that is gone:", *dangling])


@pytest.mark.parametrize("name", sorted(HISTORICAL))
def test_a_historical_test_is_still_readable_where_the_row_says(name):
    """A row here promises a reader can recover the test. Unverified, that
    promise is worth exactly as much as the dead name it replaced."""
    import subprocess

    ref, path, _why = HISTORICAL[name]
    shown = subprocess.run(
        ["git", "show", f"{ref}:{path}"],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert shown.returncode == 0, (
        f"HISTORICAL[{name!r}] points at `{ref}:{path}`, which git cannot read: "
        f"{shown.stderr.strip()[:200]}")
    assert f"def {name}(" in shown.stdout, (
        f"HISTORICAL[{name!r}] says to read it at `{ref}:{path}`, and it is not "
        f"defined there. Find the commit that still has it and correct the row.")


def test_a_historical_row_is_not_also_a_live_test():
    """The mirror of `RESERVED`'s disjointness check. A name that is both declared
    dead and defined means the row outlived what it was for, and the guard above
    is forgiving a reference it should be checking."""
    defined = _defined()
    both = sorted(set(HISTORICAL) & set(defined))
    assert not both, (
        f"declared historical AND defined: {both}. Delete the row -- the test is "
        f"back, so references to it need no exception.")


def test_a_historical_row_is_not_orphaned():
    """A row nobody cites is a row that should go, by the same rule `RESERVED`
    states: an exception left behind is a permanent one nobody owns."""
    cited = {name for _where, _line, name in _references()}
    orphaned = sorted(set(HISTORICAL) - cited)
    assert not orphaned, (
        f"HISTORICAL rows nothing references any more: {orphaned}. The last "
        f"comment naming them went; the row should go with it.")


def test_the_guard_reads_something():
    """A parameterised sweep that matched nothing would pass every case, which is
    how a guard becomes decoration. The floor is what makes the sweep a claim: a
    pattern that silently stops matching fails here instead of going green."""
    total = sum(1 for _ in _references())
    assert total >= REFERENCE_FLOOR, (
        f"only {total} backticked test references found across "
        f"{len(_test_files())} files, against a floor of {REFERENCE_FLOOR}. The "
        f"pattern has probably stopped matching.")
