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
    ("source_site", "marketlens_source_key"): "price_source_key",
    # `R-62` / migration `0014`: one source registry. `site_profile` merged into
    # `source_site`, so every column of it and every column pointing AT it is named
    # here, one at a time, and nothing about the frozen record is rewritten.
    ("site_profile", "site_profile_id"): "source_id",
    ("site_profile", "site_key"): "source_key",
    ("site_profile", "display_name"): "source_name",
    ("site_profile", "marketlens_source_key"): "price_source_key",
    ("dataset_definition", "site_profile_id"): "source_id",
    ("dataset_relationship", "site_profile_id"): "source_id",
}

#: DELIBERATE DISAPPEARANCES, under the same rule as `RENAMED` and for the same reason:
#: an object ABSORBED into another is not lost, and an object that simply vanished is.
#: Anything gone without a line here is still reported.
#:
#: The value is where it went, or `None` for an object that had nowhere to go and was
#: correct to drop — an index on a table that no longer exists indexes nothing.
MERGED = {
    # `R-62` / `0014`. Every column of `site_profile` lives in `source_site`; `RENAMED`
    # above says under which name, and the column check follows it there.
    "site_profile": "source_site",
    "ix_site_profile_page": None,
}

#: A column whose REPLACEMENT is deliberately a different shape. `RENAMED` cannot say
#: this: it asserts the new column carries the old one's type, NOT NULL and DEFAULT,
#: which is exactly what a reshape breaks. Kept separate so that the ordinary rename --
#: where the shape MUST match -- keeps its full strength.
RESHAPED = {
    # `R-71`: `active INTEGER NOT NULL DEFAULT 1` became
    # `lifecycle TEXT NOT NULL DEFAULT 'draft'`, because `active = 0` could not tell
    # "never configured" from "you switched it off" -- and both muqawil rows were the
    # first kind. `1 -> 'active'`, `0 -> 'paused'`, migrated in `0014`.
    ("source_site", "active"): "lifecycle",
    # THE TWO SIDES DISAGREED AND THE UNION TOOK THE WEAKER DEFAULT.
    # `site_profile.display_name` was `NOT NULL` with no default and
    # `source_site.source_name` was `NOT NULL DEFAULT ''`. Keeping the general side's
    # shape would refuse a price row that never had a name -- `SPARK_ESHOP` stores `''`
    # today -- so the merged column keeps the price side's default. The NOT NULL survives
    # on both; only the default is new to the general half.
    #
    # `base_url` is NOT here on purpose. It was the same kind of disagreement and it was
    # resolved the other way, by taking the STRONGER constraint: zero rows of either
    # table hold a NULL, measured, so `NOT NULL` costs nothing and keeps the guarantee.
    ("site_profile", "display_name"): "source_name",
    # AND THE SAME TWO COLUMNS SEEN FROM THE PRICE SIDE, because the frozen record holds
    # both streams and a merge changes each of them relative to the other.
    #
    # `base_url` GAINED `NOT NULL DEFAULT ''`. A strengthening is still a change and the
    # guard is right to report it; it is recorded rather than excused, and the measurement
    # behind it is in `0014`: zero rows of either table hold a NULL. The default is what
    # keeps a registration that does not yet know the URL from being refused.
    ("source_site", "base_url"): "base_url",
    # The same column seen from the general side, which had it `NOT NULL` already
    # and gains only the default.
    ("site_profile", "base_url"): "base_url",
    # `source_name_ar` GAINED `DEFAULT ''`. It was `NOT NULL` with no default, so every
    # INSERT had to name it -- and a general-side registration has no Arabic name to give.
    # `SPARK_ESHOP` already stores `''`, so the column's own history says that is how
    # "not known" is spelled here.
    ("source_site", "source_name_ar"): "source_name_ar",
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
        missing = sorted(n for n in set(objects) - have if n not in MERGED)
        assert not missing, f"the {stream} stream's {missing} are not in the one schema"

    # AND A MERGE MUST HAVE SOMEWHERE TO HAVE MERGED INTO. Without this, adding a name
    # to `MERGED` would excuse a deletion as easily as it excuses an absorption -- the
    # map would become the hole rather than the record of one.
    for gone, into in MERGED.items():
        if into is not None:
            assert into in have, (
                f"{gone} is recorded as merged into {into}, which is not in the schema")


def test_every_column_of_every_table_survives(engine_schema, inventory):
    """A TABLE THAT IS PRESENT CAN STILL BE WRONG, and the name check above
    would pass it. Type, NOT NULL and DEFAULT are compared too, because a column
    that lost its default writes NULL where the old one wrote a value — which is
    not an error anywhere, just wrong data from then on."""
    for stream, objects in inventory.items():
        for name, entry in sorted(objects.items()):
            if entry["type"] != "table":
                continue
            # A MERGED TABLE'S COLUMNS ARE LOOKED FOR WHERE THEY WENT, and `RENAMED`
            # stays keyed on the ORIGINAL table, so the frozen record is still read as
            # what it is: a description of the table that used to exist.
            target = MERGED.get(name, name)
            if target is None:
                continue
            was, now = entry["columns"], _columns(engine_schema, target)

            here = {c: RENAMED.get((name, c), c) for c in was}
            reshaped = {c for c in was if (name, c) in RESHAPED}
            here.update({c: RESHAPED[(name, c)] for c in reshaped})
            missing = sorted(c for c, now_name in here.items() if now_name not in now)
            assert not missing, f"{stream}.{name} lost columns {missing}"

            # A reshaped column's replacement is compared for EXISTENCE above and not
            # for shape, which is the whole point of listing it.
            changed = sorted(c for c in was
                             if c not in reshaped and was[c] != now[here[c]])
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
                  "relationship_field_pair", "source_site"):
        assert table in have, f"{table} did not survive the collapse"


def test_the_priced_offers_are_still_there(engine_schema):
    """The other half of M5's "done when": every existing price test still
    passes. This is the shape those tests need before any of them can run."""
    have = _objects(engine_schema)
    for table in ("price_observation", "source_offer", "offer_state",
                  "source_product", "source_product_attribute", "crawl_run"):
        assert table in have, f"{table} did not survive the collapse"
