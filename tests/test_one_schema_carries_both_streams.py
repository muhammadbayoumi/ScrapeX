"""The one schema still carries everything the two streams carried.

M5 collapsed General and MarketLens into one database. `db/engine/schema.sql`
was DERIVED from their two streams rather than retyped, because sixty-two
migrations stood behind that shape and a hand would have dropped some of it in
silence — a table nobody notices is gone until a report comes back empty, or a
trigger whose absence turns an append-only log into an editable one.

WHY THIS FILE NO LONGER RE-DERIVES. It used to run both old streams on every
test run and compare. That worked, and it held the whole collapse hostage: two
migration streams, sixty-two SQL files and two Python classes had to be kept
alive and working forever, shipping in nothing, purely to re-prove a fact about
one afternoon in August 2026.

So the fact was FROZEN instead. `db/engine/derived-from.json` records every
table, column, index, trigger and view those two streams produced — 134 objects,
with each column's type, NOT NULL and DEFAULT — written at the moment of the
collapse, while both streams still existed. The streams were then deleted.

The guarantee is unchanged and now outlives the thing it is about: whatever
happens to the engine schema from here, it can still be held against what the
two databases actually had. What it no longer does is force the name
`MarketLens` to stay in a codebase that has nothing by that name any more.

Nothing here is asserted against the file's text. Every check runs against a
database BUILT from it, because a CREATE TABLE SQLite would reject, or a trigger
naming a column that is not there, is invisible to any amount of reading.
"""

from __future__ import annotations

import json
import pathlib
import sqlite3

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]

#: DELIBERATE CHANGES SINCE THE COLLAPSE, named one at a time.
#:
#: The frozen record says what the two streams HAD, and it is never rewritten —
#: it is a record of history, and a history edited to agree with the present
#: proves nothing. So when a column is legitimately renamed afterwards, it is
#: written down HERE instead, and the checks follow it.
#:
#: That keeps the guard sharp in the only way that matters: anything that
#: disappears WITHOUT a line in this map is still reported as lost. Regenerating
#: the record instead would have made the guard pass by moving it.
RENAMED = {
    # M5 left nothing called MarketLens, so a column named after it was telling
    # readers to go looking for a database that had been deleted.
    ("site_profile", "marketlens_source_key"): "price_source_key",
}
SCHEMA = ROOT / "db" / "engine" / "schema.sql"
FROZEN = ROOT / "db" / "engine" / "derived-from.json"


@pytest.fixture(scope="module")
def engine_schema(tmp_path_factory):
    """The database as the PRODUCT builds it: schema.sql and every migration
    after it, through EngineDatabase.

    It used to be `executescript(schema.sql)`, which was enough while there were
    no migrations and quietly wrong the moment there was one — it would have
    compared the frozen record against v1 forever and never seen anything that
    changed afterwards.
    """
    from scrapex.databases.domain import EngineDatabase

    db = EngineDatabase(tmp_path_factory.mktemp("engine") / "scrapex-engine.db")
    db.initialize()
    return sqlite3.connect(f"file:{db.path}?mode=ro", uri=True)


@pytest.fixture(scope="module")
def inventory() -> dict:
    return json.loads(FROZEN.read_text(encoding="utf-8"))["streams"]


def _objects(con) -> set[str]:
    return {n for (n,) in con.execute(
        "SELECT name FROM sqlite_master WHERE sql IS NOT NULL")}


def _columns(con, table: str) -> dict[str, dict]:
    return {r[1]: {"type": r[2], "notnull": r[3], "default": r[4]}
            for r in con.execute(f'PRAGMA table_info("{table}")')}


def test_it_is_a_schema_sqlite_will_actually_accept(engine_schema):
    """Reading SQL proves nothing about whether it runs. The file is executed
    into a real database before anything else is asserted about it."""
    assert len(_objects(engine_schema)) > 100


def test_every_object_from_both_streams_survives(engine_schema, inventory):
    """Tables, indexes, triggers and views, by name, from both sides.

    A trigger is the easiest to lose and the most expensive: the generic stream
    carried sixteen, and several are what make an append-only log append-only.
    Dropping one turns a guarantee into a comment.
    """
    have = _objects(engine_schema)
    for stream, objects in inventory.items():
        missing = sorted(set(objects) - have)
        assert not missing, f"the {stream} stream's {missing} are not in the one schema"


def test_every_column_of_every_table_survives(engine_schema, inventory):
    """A TABLE THAT IS PRESENT CAN STILL BE WRONG, and the name check above
    would pass it. Type, NOT NULL and DEFAULT are compared too, because a column
    that lost its default writes NULL where the old one wrote a value — which is
    not an error anywhere, just wrong data from then on."""
    for stream, objects in inventory.items():
        for name, entry in sorted(objects.items()):
            if entry["type"] != "table":
                continue
            was, now = entry["columns"], _columns(engine_schema, name)

            here = {c: RENAMED.get((name, c), c) for c in was}
            missing = sorted(c for c, now_name in here.items() if now_name not in now)
            assert not missing, f"{stream}.{name} lost columns {missing}"

            changed = sorted(c for c in was if was[c] != now[here[c]])
            assert not changed, (
                f"{stream}.{name} columns {changed} changed shape: "
                + ", ".join(f"{c}: {was[c]} -> {now[here[c]]}" for c in changed))


def test_the_record_of_what_was_collapsed_is_not_empty(inventory):
    """A frozen fixture that quietly became `{}` would make every check above
    pass by having nothing to check. The counts are named so emptying the file
    fails rather than succeeds."""
    assert set(inventory) == {"price", "generic"}
    assert len(inventory["price"]) == 91, "the price stream's record changed"
    assert len(inventory["generic"]) == 43, "the generic stream's record changed"

    tables = [n for s in inventory.values() for n, e in s.items()
              if e["type"] == "table"]
    assert len(tables) == 53, "the table count changed"


def test_the_generic_tables_the_plan_names_are_all_here(engine_schema):
    """PLATFORM-PLAN M5: "bring the eleven generic tables in beside the priced
    offers". Named individually rather than counted, because a count is
    satisfied by any eleven tables."""
    have = _objects(engine_schema)
    for table in ("generic_page_snapshot", "generic_record", "generic_record_revision",
                  "generic_ingestion", "dataset_definition", "dataset_schema_version",
                  "schema_version_field", "field_definition", "dataset_relationship",
                  "relationship_field_pair", "site_profile"):
        assert table in have, f"{table} did not survive the collapse"


def test_the_priced_offers_are_still_there(engine_schema):
    """The other half of M5's "done when": every existing price test still
    passes. This is the shape those tests need before any of them can run."""
    have = _objects(engine_schema)
    for table in ("price_observation", "source_offer", "offer_state",
                  "source_product", "source_product_attribute", "crawl_run"):
        assert table in have, f"{table} did not survive the collapse"
