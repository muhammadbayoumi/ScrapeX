"""There is one migration plan, and the baseline's number is read where it is declared.

TWO BUILDERS WALKED THE SAME FOLDER. `scrapex/db.py` `_migration_files` and
`scrapex/databases/domain.py` `_folder_migrations` each resolved
`db/engine/migrations/` into an ordered plan, separately written, and they were not
equivalent: `db`'s RAISES on a file that does not match `NNNN_name.sql`, the other
globbed silently past it.

The coincidence was already load-bearing. `tests/conftest.py` `_stream_fingerprint`
decides whether a cached migrated database may be reused by resolving `db`'s
builder, while the migration that filled that cache ran through the other one.

AND THE BASELINE'S NUMBER WAS THE LITERAL 1 IN THREE PLACES: both builders, and
`db/engine/schema.sql` itself as `PRAGMA user_version = 1`. Only the third is the
one SQLite obeys. `latest_schema_version()` derives from it and flows into
`storage.py` `health()`, which decides whether a warehouse is too new for this
engine to open -- so a stale copy does not merely disagree, it tells the owner his
database was written by a newer ScrapeX and must not be downgraded.

`.githooks/pre-push` had already reached this conclusion and says so: it asks
`scrapex database-status` rather than reading `PRAGMA user_version` itself, because
that *"keeps one owner for the comparison"*. This file is that rule applied to the
two places that had not got it.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from scrapex import db as dbmod
from scrapex.databases.domain import (
    DatabaseMigrationError,
    DomainDatabase,
    EngineDatabase,
    Migration,
    _engine_plan,
)


class _Probe(DomainDatabase):
    """A domain type with no file behind it: only `__init__`'s rule is under test."""

    kind = "probe"
    application_id = 1


def _version_the_file_declares() -> int:
    """An INDEPENDENT reader of the baseline's version.

    Deliberately not `dbmod.declared_schema_version`, and not its regex either. The
    whole failure this file is about is a fact asserted in two places where only one
    of them is obeyed, so a guard that calls the implementation it is checking would
    reproduce the failure instead of catching it. This walks lines and splits on
    `=`, which shares no code with the subject.
    """
    found = []
    for line in dbmod.SCHEMA_FILE.read_text(encoding="utf-8").splitlines():
        head, _, tail = line.partition("=")
        if head.strip().lower().replace("  ", " ") == "pragma user_version":
            found.append(int(tail.strip().rstrip(";").strip()))
    assert len(found) == 1, f"the baseline declares {len(found)} versions, expected 1"
    return found[0]


def test_the_engine_plan_follows_the_one_builder(monkeypatch):
    """`domain` must READ the plan, not rebuild it.

    NOT A TAUTOLOGY, and this is the assertion that makes the change stick: the
    builder is replaced with one that returns a different stream, and the engine's
    plan has to change with it. A `domain` that walks the folder itself again passes
    every other test in the suite and fails this one.
    """
    # PATCHED LONGER, NOT SHORTER. Slicing to `whole[:3]` proved the plan follows
    # the builder only while the builder had more than three entries to slice; after
    # `R-84`'s squash the shipped plan is one migration and the slice became the
    # whole list, turning this into a tautology and then an IndexError. Appending
    # cannot run out of stream, and it still fails on a `domain` that walks the
    # folder itself -- which is the whole point of the assertion.
    whole = dbmod._migration_files()
    invented = (whole[-1][0] + 1, whole[-1][1].with_name("0099_invented.sql"))
    monkeypatch.setattr(dbmod, "_migration_files", lambda: [*whole, invented])

    assert [item.number for item in _engine_plan()] == [
        *(n for n, _ in whole), invented[0]]
    assert EngineDatabase("unused.db").latest_schema_version == invented[0]


def test_the_baseline_number_comes_from_the_file_that_declares_it():
    """The plan's first number is the one the SQL sets, read two different ways."""
    declared = _version_the_file_declares()

    assert dbmod.declared_schema_version(dbmod.SCHEMA_FILE) == declared
    assert dbmod._migration_files()[0][0] == declared
    assert _engine_plan()[0].number == declared


def test_the_declared_version_must_be_stated_exactly_once(tmp_path: Path):
    """Zero and two are both refused, and the count is why.

    Seven of the fifteen shipped migrations set no `PRAGMA user_version` at all and
    are silently corrected by the runner, so "take the last match" would happily
    read a number out of a file that never stated one.
    """
    none = tmp_path / "none.sql"
    none.write_text("CREATE TABLE x(a);\n", encoding="utf-8")
    with pytest.raises(ValueError, match="declares 0 "):
        dbmod.declared_schema_version(none)

    twice = tmp_path / "twice.sql"
    twice.write_text("PRAGMA user_version = 3;\nPRAGMA user_version = 4;\n",
                     encoding="utf-8")
    with pytest.raises(ValueError, match="declares 2 "):
        dbmod.declared_schema_version(twice)


def test_a_plan_that_starts_above_one_is_accepted():
    """What the old rule forbade and nothing needed it to.

    `gapless from 1` was true of the stream that existed when it was written, and a
    squashed baseline gives up exactly that half. The half that matters -- no
    MISSING migration between two present ones -- is kept below.
    """
    _Probe("unused.db", (Migration(16, dbmod.SCHEMA_FILE),))
    _Probe("unused.db", (Migration(16, dbmod.SCHEMA_FILE),
                         Migration(17, dbmod.SCHEMA_FILE)))


def test_a_hole_in_the_plan_is_still_refused():
    """The half of the old rule that was doing real work.

    A hole means a database can reach a version this build cannot explain, which is
    what `R-24` and `OP-30` both turn on.
    """
    with pytest.raises(DatabaseMigrationError, match="contiguous"):
        _Probe("unused.db", (Migration(16, dbmod.SCHEMA_FILE),
                             Migration(18, dbmod.SCHEMA_FILE)))
    with pytest.raises(DatabaseMigrationError, match="contiguous"):
        _Probe("unused.db", (Migration(1, dbmod.SCHEMA_FILE),
                             Migration(3, dbmod.SCHEMA_FILE)))


def test_a_plan_numbered_from_zero_is_refused():
    """0 is what `PRAGMA user_version` reads on a database nobody has migrated, so a
    plan starting there could not tell "never touched" from "already at the
    baseline"."""
    with pytest.raises(DatabaseMigrationError, match="1 or above"):
        _Probe("unused.db", (Migration(0, dbmod.SCHEMA_FILE),))


def test_a_migration_numbered_at_or_below_the_baseline_is_refused(
        tmp_path: Path, monkeypatch):
    """The rule that replaces "0001 is reserved for schema.sql".

    A file numbered below the baseline can never run -- `_migrate` skips anything at
    or under the current version -- so it is a migration the author believes is
    shipping and which is dead on arrival. It used to be checked against the literal
    1; now it is checked against whatever the baseline says.
    """
    baseline = tmp_path / "schema.sql"
    baseline.write_text("PRAGMA user_version = 9;\n", encoding="utf-8")
    folder = tmp_path / "migrations"
    folder.mkdir()
    (folder / "0005_too_early.sql").write_text("PRAGMA user_version = 5;\n",
                                               encoding="utf-8")
    monkeypatch.setattr(dbmod, "SCHEMA_FILE", baseline)
    monkeypatch.setattr(dbmod, "MIGRATIONS_DIR", folder)

    with pytest.raises(ValueError, match="at or below the baseline"):
        dbmod._migration_files()


def test_the_plan_is_contiguous_from_the_baseline_as_shipped():
    """The shipped stream, held against the rule rather than against a literal."""
    plan = dbmod._migration_files()
    numbers = [n for n, _ in plan]
    first = _version_the_file_declares()

    assert numbers == list(range(first, first + len(numbers))), (
        f"the shipped plan is not contiguous from the baseline's declared version "
        f"{first}: {numbers}")
    assert dbmod.latest_schema_version() == numbers[-1]
