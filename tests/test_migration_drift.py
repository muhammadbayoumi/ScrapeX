r"""T5's two-way drift check, which ENGINEERING.md mandates and nothing implemented.

ENGINEERING.md:41 requires: "apply all migrations to the previous release's
fixture DB and diff against a fresh schema.sql build (two-way drift check)".
No fixture database is checked into this repo (`git ls-files | grep '\.db$'` is
empty), so the mandate has been on paper only — and the consequence is that the
ONLY thing every migration is ever exercised against is an EMPTY database. A
migration that is wrong solely in the presence of rows cannot fail here today.

Rather than commit a binary that goes stale, the "previous release" is synthesised
from the stream itself: stop at version N, put rows in, then apply the rest. That
is exactly the shape an existing owner upgrades through, and the shape a fresh
install never takes.

IT WAS OFF FOR A MONTH AND NOTHING SAID SO. The note that stood here promised
"it moves across the day engine migrations 0002+ exist" — and the gate below it
compared the stream's length against PREVIOUS_RELEASE = 30, the number the
DELETED price stream had. Engine migrations 0002 through 0016 arrived, the engine
stream reached 16, and 16 <= 30 kept skipping. The promise was in prose and the
mechanism was a constant nobody re-derived; measured on 2026-09-02, both tests in
this file had been reporting `ss` since the M5 collapse.

THE FIRST REAL RUN FOUND A SHIPPED DEFECT, which is the argument for this file
rather than a story about it: 0014_one_source_registry.sql rebuilds source_site
with `base_url TEXT NOT NULL DEFAULT ''` and then copies the old column through
by name, and a DEFAULT never applies to a column an INSERT names. base_url was
nullable through v13, so a legal row fails the upgrade. Reproduced at every stop
point from v2 to v13. The migration's own comment shows it was reasoned about and
the mechanism mistaken: zero NULLs were measured in one warehouse and the
constraint was called free on that evidence.

SO THE SKIP NOW HAS AN ASSERTION BEHIND IT. PREVIOUS_RELEASE is checked against
the shipped stream by a test of its own, because that is the one comparison that
would have failed the day 30 stopped being a version this stream has. A skip
cannot be the only thing standing between a mandate and nothing.
"""
from __future__ import annotations

import sqlite3

import pytest

from scrapex.databases.domain import EngineDatabase

#: The version an existing owner is upgrading FROM. It must be a real version of
#: the shipped stream with something after it, and
#: `test_the_stop_point_is_a_version_this_stream_actually_has` enforces that --
#: see this file's header for what one unenforced constant cost.
#:
#: WHY 14 AND NOT THE MIDPOINT, which is the honest answer rather than the
#: flattering one: every stop point from v2 to v13 currently fails, because
#: migration 0014 cannot upgrade a row whose base_url is NULL. So the span
#: actually exercised over real rows is v15 and v16 -- two migrations, not eight.
#: That is weaker than this file wants to be, and it is written down rather than
#: hidden, because the alternative is a number chosen to make the suite green and
#: a reader who cannot tell that from a number chosen on evidence. It rises the
#: moment 0014 stops being a wall, which the pending baseline squash does by
#: absorbing it.
PREVIOUS_RELEASE = 14

#: The deepest stop point migration 0014 refuses, kept as a test rather than as a
#: sentence -- see `test_a_null_base_url_still_stops_the_registry_merge`.
BLOCKED_BY_0014 = 13


def _fingerprint(conn: sqlite3.Connection) -> dict:
    """The schema as STRUCTURE, not as text.

    Deliberately not a diff of sqlite_master.sql: a column added by ALTER TABLE
    reads differently from the same column declared inline, and that difference
    is a formatting artefact, not drift. Columns are compared as a sorted set for
    the same reason — SQLite appends ALTER-added columns, so ORDER legitimately
    differs between an upgraded and a fresh database.
    """
    out: dict = {"tables": {}, "indexes": {}, "triggers": set(), "views": set()}
    for kind, name in conn.execute(
            "SELECT type, name FROM sqlite_master "
            "WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name"):
        if kind == "table":
            out["tables"][name] = sorted(
                (r[1], (r[2] or "").upper(), r[3], r[4], r[5])
                for r in conn.execute(f"PRAGMA table_info('{name}')"))
        elif kind == "index":
            # An expression index reports a NULL column name; keep its
            # position so two such indexes are still told apart.
            out["indexes"][name] = sorted(
                (r[0], r[2] or "<expr>") for r in conn.execute(f"PRAGMA index_info('{name}')"))
        elif kind == "trigger":
            out["triggers"].add(name)
        elif kind == "view":
            out["views"].add(name)
    return out


def _seed_every_table(conn: sqlite3.Connection, tables: list[str]) -> int:
    """One row per named table, built from the schema rather than hand-written.

    Hand-written seeds pin themselves to one version and rot; this reads
    PRAGMA table_info at whatever version it is handed and supplies a value for
    every NOT NULL column that has no default. It only needs to be plausible —
    the point is that the tables are NOT EMPTY when the later migrations run.
    """
    seeded = 0
    for index, table in enumerate(tables):
        cols, values = [], []
        for _cid, name, decl, notnull, default, pk in conn.execute(
                f"PRAGMA table_info('{table}')"):
            if pk and "INT" in (decl or "").upper():
                continue                      # let the rowid alias assign itself
            if not notnull or default is not None:
                continue
            cols.append(name)
            kind = (decl or "TEXT").upper()
            # DISTINCT PER COLUMN, and it has to be. Every crude row used to say
            # "x", so the moment a migration MERGED two tables the two rows
            # collided on a UNIQUE key and 0014 reported
            #     UNIQUE constraint failed: source_site.source_key
            # -- a failure belonging to the seed and not to the migration. Turning
            # this file back on reported two defects before this line was fixed,
            # and only one of them was real.
            values.append(1 if ("INT" in kind or "REAL" in kind or "NUM" in kind)
                          else f"{table}.{name}")
        marks = ", ".join("?" for _ in cols)
        names = ", ".join(f'"{c}"' for c in cols)
        # A SAVEPOINT per table, not a rollback: a crude row that a foreign key
        # refuses must undo ITSELF and nothing else. A plain rollback discarded
        # every row seeded before it — the first draft of this reported 12
        # inserts and left 4 rows, which is exactly the "the test cannot fail"
        # trap the whole file exists to close.
        savepoint = f"seed_{index}"
        conn.execute(f"SAVEPOINT {savepoint}")
        try:
            conn.execute(f"INSERT INTO {table} ({names}) VALUES ({marks})", values)
        except sqlite3.DatabaseError:
            conn.execute(f"ROLLBACK TO {savepoint}")
        else:
            seeded += 1
        conn.execute(f"RELEASE {savepoint}")
    conn.commit()
    return seeded


def _stop_point_is_valid(count: int) -> bool:
    """Whether PREVIOUS_RELEASE names a version this stream can stop inside.

    Two migrations are the minimum: with one, a fresh build and an upgraded one
    are the same object and the comparison asserts nothing.
    """
    return 2 <= PREVIOUS_RELEASE < count


def test_the_stop_point_is_a_version_this_stream_actually_has():
    """The one assertion that would have caught a month of silence.

    It compares two things maintained by different hands -- a constant in this
    file and the length of the shipped stream -- which is the only shape that
    catches a constant left behind by a deletion. Every other test here READS
    PREVIOUS_RELEASE and therefore agrees with whatever it says.

    IT FAILS RATHER THAN SKIPS, deliberately. A skip is what hid the problem for
    a month; when the stream stops being long enough to measure drift inside,
    that is a decision someone has to take and write down, not a line of `ss` in
    a run nobody reads.
    """
    count = len(EngineDatabase("unused.db")._migrations)
    assert _stop_point_is_valid(count), (
        f"PREVIOUS_RELEASE = {PREVIOUS_RELEASE} is not a version the shipped "
        f"engine stream has: it holds {count} migration(s), so a stop point must "
        f"be at least 2 and at most {count - 1}. This exact mismatch turned the "
        f"two-way drift check ENGINEERING.md T5 mandates off for a month -- 30 "
        f"was the deleted price stream's number. If the stream is now too short "
        f"to measure drift inside, say what replaces this check before lowering "
        f"the bar: a frozen fingerprint of the shape the chain produced is the "
        f"pattern this repository already uses (db/engine/derived-from.json).")


def _requires_a_stream_it_can_stop_inside(db) -> None:
    """Skips only when the assertion above is ALREADY FAILING, so a skip here
    is never the whole report.

    That is the difference from the version of this that rotted: the skip used to
    be the only thing that noticed, and it noticed quietly.
    """
    if not _stop_point_is_valid(len(db._migrations)):
        pytest.skip(
            f"PREVIOUS_RELEASE = {PREVIOUS_RELEASE} is not a stop point in a "
            f"stream of {len(db._migrations)}; see the failure in "
            "test_the_stop_point_is_a_version_this_stream_actually_has")


def _upgraded_from_previous_release(path, monkeypatch) -> EngineDatabase:
    db = EngineDatabase(path)
    whole = db._migrations
    _requires_a_stream_it_can_stop_inside(db)

    monkeypatch.setattr(db, "_migrations", whole[:PREVIOUS_RELEASE])
    db.initialize()
    with db.connect() as conn:
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' AND name <> 'database_migration'")]
        seeded = _seed_every_table(conn, tables)
    assert seeded, "nothing could be seeded, so the upgrade ran over an empty database again"

    monkeypatch.setattr(db, "_migrations", whole)
    db.initialize()
    return db


def test_an_upgraded_database_matches_a_freshly_built_one(tmp_path, monkeypatch):
    """The drift this exists to catch: a migration that adds what schema.sql
    already declares, or declares what no migration adds. A fresh install and an
    upgraded install would then be two different products wearing one version
    number, and nothing in the suite would say so."""
    _requires_a_stream_it_can_stop_inside(EngineDatabase(tmp_path / "probe.db"))
    fresh = EngineDatabase(tmp_path / "fresh.db")
    fresh.initialize()
    upgraded = _upgraded_from_previous_release(tmp_path / "upgraded.db", monkeypatch)

    with fresh.connect() as a, upgraded.connect() as b:
        want, got = _fingerprint(a), _fingerprint(b)

    assert set(want["tables"]) == set(got["tables"]), (
        f"tables only in a fresh build: {sorted(set(want['tables']) - set(got['tables']))} · "
        f"only in an upgraded one: {sorted(set(got['tables']) - set(want['tables']))}")
    for table in sorted(want["tables"]):
        assert want["tables"][table] == got["tables"][table], (
            f"table {table!r} differs between a fresh build and an upgraded one:\n"
            f"  fresh   : {want['tables'][table]}\n  upgraded: {got['tables'][table]}")
    assert want["indexes"] == got["indexes"], "index drift between fresh and upgraded"
    assert want["triggers"] == got["triggers"], "trigger drift (A7's append-only guards live here)"
    assert want["views"] == got["views"], "view drift between fresh and upgraded"


def test_the_whole_stream_survives_migrating_over_real_rows(tmp_path, monkeypatch):
    """The gap this closes: every other test in the suite applies migrations to
    an EMPTY database, so a migration that only breaks in the presence of rows
    (a NOT NULL added without a default, a CHECK the existing data violates, a
    rebuild that drops rows) passes every test and fails on the owner's machine.
    """
    db = _upgraded_from_previous_release(tmp_path / "upgraded.db", monkeypatch)
    with db.connect() as conn:
        assert int(conn.execute("PRAGMA user_version").fetchone()[0]) == db.latest_schema_version
        broken = conn.execute("PRAGMA foreign_key_check").fetchall()
        assert not broken, f"the upgrade left rows pointing at nothing: {broken[:3]}"
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert db.health().ok, db.health().action


def test_a_null_base_url_still_stops_the_registry_merge(tmp_path):
    """The wall that holds PREVIOUS_RELEASE at 14, as a test rather than a note.

    `0014_one_source_registry.sql` rebuilds `source_site` with
    `base_url TEXT NOT NULL DEFAULT ''` and then copies the old column through by
    name:

        INSERT INTO source_site_rebuilt (... base_url ...)
        SELECT                            ... base_url ...

    A DEFAULT applies only to a column an INSERT OMITS, so the NULL is carried
    into a NOT NULL column and the migration fails. `source_site.base_url` was
    nullable through v13 -- measured, `notnull=0` -- so the row that triggers it
    is legal, not corrupt.

    THE MIGRATION'S OWN COMMENT SHOWS IT WAS REASONED ABOUT AND THE MECHANISM
    MISTAKEN: "on his warehouse zero rows of either table hold a NULL -- 0 of 12
    and 0 of 2 -- so the stronger constraint costs nothing". True of that data,
    and the constraint is free only on that data.

    IT ASSERTS THE EXACT MESSAGE, NOT MERELY THAT SOMETHING RAISED. A bare
    `pytest.raises` here would keep passing if the wall moved to a different
    column or a different migration, and would then be recording a defect that no
    longer exists while hiding the one that does.

    WHY THIS IS NOT FIXED IN PLACE: `0014` is applied and its digest is in the
    ledger of every existing warehouse, so editing one character of it makes those
    databases refuse to open (`domain.py` `_verify_checksums`). The pending
    baseline squash absorbs it, which removes the file and the wall together --
    and this test must be DELETED in that change, because the stop point it
    explains stops existing with it.
    """
    db = EngineDatabase(tmp_path / "at_the_wall.db")
    whole = db._migrations
    assert len(whole) > BLOCKED_BY_0014, (
        "the stream no longer reaches past the wall this test describes; if "
        "0014 has been absorbed, delete this test with it")
    db._migrations = whole[:BLOCKED_BY_0014]
    db.initialize()
    with db.connect() as conn:
        columns = {r[1]: r[3] for r in conn.execute("PRAGMA table_info(source_site)")}
        assert columns["base_url"] == 0, (
            "base_url is no longer nullable at this version, so the row below "
            "is not the legal row this test is about")
        conn.execute(
            "INSERT INTO source_site (source_key, source_name_ar, base_url) "
            "VALUES ('a-shop-with-no-known-url', 'متجر', NULL)")
        conn.commit()

    db._migrations = whole
    with pytest.raises(sqlite3.IntegrityError, match=
            r"NOT NULL constraint failed: source_site_rebuilt\.base_url"):
        db.initialize()
