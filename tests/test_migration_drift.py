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

NOTE (M5): this deliberately stays on the PRICE stream, which still has
fifty-nine migrations. It tests a property of the MIGRATION FRAMEWORK — that a
database upgraded step by step ends up identical to one built fresh — and that
needs a long stream to stop partway through. The engine stream is one migration
today, so pointing this at it would assert nothing. It moves across the day
engine migrations 0002+ exist.
"""
from __future__ import annotations

import sqlite3

import pytest

from scrapex.databases.domain import MarketLensDatabase

# Far enough in that the price chain exists, far enough back that a real span of
# migrations runs over the seeded rows.
PREVIOUS_RELEASE = 30


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
            values.append(1 if ("INT" in kind or "REAL" in kind or "NUM" in kind) else "x")
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


def _upgraded_from_previous_release(path, monkeypatch) -> MarketLensDatabase:
    db = MarketLensDatabase(path)
    whole = db._migrations
    assert len(whole) > PREVIOUS_RELEASE, "the stream is shorter than the stop point"

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
    fresh = MarketLensDatabase(tmp_path / "fresh.db")
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
