"""The squashed baseline still carries everything the chain it replaced produced.

`R-84` allows the migration chain to be collapsed into `db/engine/schema.sql` before
publication and never after it. This is the evidence for that collapse, and it has to
outlive the thing it is about: the fifteen migrations are gone, so nothing can re-run
them to prove the baseline equals them.

SO THE FACT WAS FROZEN, the same way `M5`'s was.
`tests/test_one_schema_carries_both_streams.py` holds the schema against
`db/engine/derived-from.json` -- 134 objects the two pre-M5 streams produced, written
while both still existed. This file does the same one collapse later:
`db/engine/squashed-from.json` records every table with its columns, every index with
its columns, every trigger, every view and every seeded row the chain left in an empty
database, written by `tools/squash_engine_baseline.py` while the chain still existed.

WHY THE FINGERPRINT IS COMPUTED HERE AND NOT IMPORTED FROM THE TOOL. The tool compares
its own output against the chain, which is the right check at generation time. Reusing
the tool's comparison HERE would make this a tautology -- a bug in that function would
produce a wrong record and a test that agrees with it. This file walks
`sqlite_master` and `PRAGMA table_info` itself, and additionally holds the record
against floors, so a record that quietly lost half its content fails rather than
passing on a smaller claim.

AND NOTHING HERE IS ASSERTED AGAINST THE FILE'S TEXT. Every check runs against a
database BUILT from it, because a `CREATE TABLE` SQLite would reject, or a trigger
naming a column that is not there, is invisible to any amount of reading.
"""
from __future__ import annotations

import json
import pathlib
import sqlite3

import pytest

from scrapex.databases.domain import EngineDatabase

ROOT = pathlib.Path(__file__).resolve().parents[1]
RECORD = ROOT / "db" / "engine" / "squashed-from.json"
BASELINE = ROOT / "db" / "engine" / "schema.sql"

#: DELIBERATE CHANGES SINCE THE SQUASH, named one at a time.
#:
#: The frozen record says what the chain PRODUCED and is never rewritten -- a history
#: edited to agree with the present proves nothing. When something legitimately
#: changes afterwards it is written down HERE instead, and the checks follow it.
#: That keeps the guard sharp in the only way that matters: anything that disappears
#: WITHOUT a line here is still reported as lost.
#:
#: Empty on the day of the squash, which is the only honest starting value.
CHANGED_SINCE_THE_SQUASH: dict[str, str] = {}

#: Floors, so a record that lost content cannot pass by describing less. Measured at
#: the squash: 67 tables, 79 indexes, 31 triggers, 2 views, 3 seeded rows.
FLOORS = {"tables": 60, "indexes": 70, "triggers": 25, "views": 2}


@pytest.fixture(scope="module")
def record() -> dict:
    assert RECORD.is_file(), (
        f"{RECORD.relative_to(ROOT)} is missing. It is the only evidence that the "
        "squashed baseline carries what the deleted chain produced; without it the "
        "baseline is a claim with nothing behind it. Regenerate with "
        "`python -m tools.squash_engine_baseline --write` ONLY from a tree that "
        "still has the chain.")
    return json.loads(RECORD.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def built(tmp_path_factory) -> sqlite3.Connection:
    """A database the baseline alone builds, through the real runner."""
    db = EngineDatabase(tmp_path_factory.mktemp("squashed") / "engine.db")
    db.initialize()
    conn = sqlite3.connect(str(db.path))
    yield conn
    conn.close()


def _tables(conn: sqlite3.Connection) -> dict[str, list]:
    out = {}
    for (name,) in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%'"):
        out[name] = sorted([r[1], (r[2] or "").upper(), r[3], r[4], r[5]]
                           for r in conn.execute(f'PRAGMA table_info("{name}")'))
    return out


def test_the_record_describes_the_baseline_beside_it(record):
    """A record of a different collapse would pass every check below and mean
    nothing."""
    head = EngineDatabase("unused.db").latest_schema_version
    assert record["head"] == head, (
        f"the record describes a chain ending at v{record['head']} and the baseline "
        f"is at v{head}")
    assert len(record["absorbed"]) > 1, (
        f"the record says {len(record['absorbed'])} migration(s) were absorbed, "
        "which is not a collapse")


def test_the_record_is_not_a_smaller_claim_than_it_was(record):
    """`PINNED_FLOOR`'s reasoning, applied to a frozen record: regenerating it from a
    broken baseline would make every other check here pass by describing less."""
    counts = {part: len(record["fingerprint"][part]) for part in FLOORS}
    small = {part: n for part, n in counts.items() if n < FLOORS[part]}
    assert not small, (
        f"the record describes fewer objects than the squash measured: {small} "
        f"against floors {FLOORS}. A record is corrected by re-deriving it from the "
        "CHAIN, never by regenerating it from the baseline it is supposed to check.")


def test_it_is_a_schema_sqlite_will_actually_accept(built):
    """The cheapest failure and the one a reader cannot see: a baseline that does not
    build."""
    assert built.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert not built.execute(
        "SELECT 1 FROM pragma_foreign_key_check LIMIT 1").fetchone()


def test_every_table_the_chain_produced_is_still_here(record, built):
    want, got = record["fingerprint"]["tables"], _tables(built)
    lost = sorted(set(want) - set(got) - set(CHANGED_SINCE_THE_SQUASH))
    assert not lost, (
        f"tables the collapsed chain produced and the baseline does not: {lost}. "
        "If one was removed on purpose, name it in CHANGED_SINCE_THE_SQUASH with "
        "the reason.")
    gained = sorted(set(got) - set(want))
    assert not gained, (
        f"tables the baseline builds and the chain never produced: {gained}. The "
        "baseline is meant to be the chain's OUTPUT, so anything new here is a "
        "hand-edit, which its own header forbids.")


def test_every_column_of_every_table_survives(record, built):
    """Columns with their types, NOT NULL and DEFAULT -- because a table that exists
    with a column missing is the failure a table-name check cannot see."""
    want, got = record["fingerprint"]["tables"], _tables(built)
    differences = []
    for name in sorted(set(want) & set(got)):
        if want[name] != [list(c) for c in got[name]]:
            wanted = {c[0] for c in want[name]}
            actual = {c[0] for c in got[name]}
            differences.append(
                f"  {name}: only in the chain {sorted(wanted - actual)}, only in the "
                f"baseline {sorted(actual - wanted)}"
                + ("" if wanted != actual else " (same columns, a type, NOT NULL or "
                                               "DEFAULT differs)"))
    assert not differences, "\n".join(
        ["these tables differ between the collapsed chain and the baseline:",
         *differences])


def test_every_index_trigger_and_view_survives(record, built):
    """A7's append-only guards are triggers, so a trigger silently absent turns an
    append-only log into an editable one and nothing else in the suite says so."""
    fingerprint = record["fingerprint"]
    for kind, query in (
            ("indexes", "SELECT name FROM sqlite_master WHERE type='index' "
                        "AND name NOT LIKE 'sqlite_%'"),
            ("triggers", "SELECT name FROM sqlite_master WHERE type='trigger'"),
            ("views", "SELECT name FROM sqlite_master WHERE type='view'")):
        want = set(fingerprint[kind])
        got = {row[0] for row in built.execute(query)}
        assert not want - got - set(CHANGED_SINCE_THE_SQUASH), (
            f"{kind} the collapsed chain produced and the baseline does not: "
            f"{sorted(want - got)}")
        assert not got - want, (
            f"{kind} the baseline builds and the chain never produced: "
            f"{sorted(got - want)}")


def test_the_rows_the_chain_seeded_are_still_seeded(record, built):
    """THE PART A SCHEMA-ONLY DUMP LOSES, and it loses it silently.

    Migration `0015` seeded the shipped retention default. A baseline generated by
    dumping DDL alone produces an engine with no retention policy at all, and nothing
    fails until something reads it -- measured while writing
    `tools/squash_engine_baseline.py`, which is why that tool emits rows.
    """
    for table, rows in sorted(record["seed"].items()):
        cols = list(rows[0])
        seen = []
        for row in built.execute(
                f'SELECT {", ".join(chr(34) + c + chr(34) for c in cols)} FROM "{table}"'):
            seen.append(dict(zip(cols, row, strict=True)))
        for wanted in rows:
            assert wanted in seen, (
                f"the chain seeded {wanted} into {table!r} and the baseline does "
                f"not. The baseline holds {seen}.")


def test_the_absorbed_migrations_are_named_and_gone(record):
    """Their NAMES are what a live ledger holds, so they are the only thing that can
    tell a database that went through the chain from one that did not."""
    # NAME AND DIGEST: the record carries both, because the digest is what the
    # runner matches a pre-squash ledger against.
    absorbed = {name for _number, name, _digest in record["absorbed"]}
    assert "schema.sql" in absorbed, (
        "the record does not name the baseline among the absorbed migrations, so it "
        "cannot say which digest a pre-squash ledger holds")
    folder = ROOT / "db" / "engine" / "migrations"
    still_there = sorted(p.name for p in folder.glob("*.sql")) if folder.is_dir() else []
    assert not (absorbed - {"schema.sql"}) & set(still_there), (
        f"these migrations are recorded as absorbed and are still in the tree: "
        f"{sorted((absorbed - {'schema.sql'}) & set(still_there))}. A file that is "
        "both collapsed and shipped would be applied twice.")
