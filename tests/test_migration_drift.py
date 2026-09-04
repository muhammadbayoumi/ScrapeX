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

import json
import pathlib
import sqlite3

import pytest

from scrapex.databases.domain import EngineDatabase

#: The version an existing owner is upgrading FROM. It must be a real version of
#: the shipped stream with something after it, and
#: `test_the_stop_point_is_a_version_this_stream_actually_has` enforces that --
#: see this file's header for what one unenforced constant cost.
#:
#: WHAT THIS NUMBER MEANS NOW THAT THE CHAIN IS ONE FILE: nothing, until a
#: migration lands after the squashed baseline. It is kept at the value it had --
#: 14, chosen because migration 0014 walled off every stop point below it -- so
#: that the first person to add 0017 finds a number and a reason rather than a
#: blank, and `test_the_stop_point_is_a_version_this_stream_actually_has` tells
#: them it needs re-choosing. It is NOT lowered to 1 to make the suite green: that
#: is the move this file's own history is a warning about.
ROOT = pathlib.Path(__file__).resolve().parents[1]

PREVIOUS_RELEASE = 14



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
    db = EngineDatabase("unused.db")
    count = len(db._migrations)
    if _stop_point_is_valid(count):
        return

    # A ONE-MIGRATION STREAM IS ALLOWED, AND ONLY AGAINST A RECORD WITH CONTENT IN
    # IT. `R-84` collapsed the chain into the baseline, so there is no longer a
    # version to stop inside -- and that is exactly the moment this guard existed
    # to make somebody answer rather than lower the bar. The answer is the frozen
    # record: `db/engine/squashed-from.json` holds every object and every seeded row
    # the collapsed chain produced, and
    # `tests/test_the_squashed_baseline_carries_the_chain.py` holds the baseline
    # against it. Checked HERE rather than taken on trust, because a file that
    # merely exists is the weakest possible replacement for a check.
    record = ROOT / "db" / "engine" / "squashed-from.json"
    assert count == 1, (
        f"PREVIOUS_RELEASE = {PREVIOUS_RELEASE} is not a version the shipped engine "
        f"stream has: it holds {count} migration(s), so a stop point must be at "
        f"least 2 and at most {count - 1}. This exact mismatch turned the two-way "
        f"drift check ENGINEERING.md T5 mandates off for a month -- 30 was the "
        f"deleted price stream's number. Choose a real stop point; do not lower "
        f"this to make the suite green.")
    assert record.is_file(), (
        "the engine stream is one migration, so drift cannot be measured inside it, "
        f"and {record.name} is not there to replace the measurement. A squashed "
        "baseline with no record of what it absorbed is a claim with no evidence.")
    frozen = json.loads(record.read_text(encoding="utf-8"))
    assert frozen.get("head") == db.latest_schema_version, (
        f"{record.name} records a chain ending at v{frozen.get('head')} and the "
        f"baseline is at v{db.latest_schema_version}. One of them is wrong, and a "
        "record that does not describe the file beside it proves nothing.")
    assert len(frozen.get("absorbed") or []) > 1, (
        f"{record.name} says the baseline absorbed "
        f"{len(frozen.get('absorbed') or [])} migration(s), which is not a collapse. "
        "If the chain was never collapsed, this stream is simply too short and "
        "PREVIOUS_RELEASE needs a real value.")


def _requires_a_stream_it_can_stop_inside(db) -> None:
    """Skips only when the assertion above is ALREADY FAILING, so a skip here
    is never the whole report.

    That is the difference from the version of this that rotted: the skip used to
    be the only thing that noticed, and it noticed quietly.
    """
    if not _stop_point_is_valid(len(db._migrations)):
        pytest.skip(
            f"the engine stream is {len(db._migrations)} migration(s), so a fresh "
            "build and an upgraded one are the same object and this comparison "
            "asserts nothing. `R-84` collapsed the chain into the baseline; what "
            "replaces the measurement is db/engine/squashed-from.json, checked by "
            "test_the_stop_point_is_a_version_this_stream_actually_has above and "
            "held against the baseline by "
            "tests/test_the_squashed_baseline_carries_the_chain.py. This skip is "
            "live again the moment a migration lands after the baseline.")


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

