"""The one schema must carry everything the two streams carried.

M5 collapses General and MarketLens into a single database. The owner's data does
not have to survive it — nothing is published, so no user can be hurt — but the
SHAPE does. Sixty-two migrations stand behind that shape, and each of them was a
decision: a column order that says who arranged it, an offer that can be
superseded, a run that says whether it had warnings.

WHAT THIS FILE IS FOR. `db/engine/schema.sql` is generated, and a generated file
is only as trustworthy as the check that it still matches its source. Without
this, the derivation runs once, the streams move on, and the schema quietly
describes a database nobody has any more — the exact "overwritten feature"
failure, arriving months later as a report that comes back empty.

Every assertion here is against a database BUILT FROM the committed file, never
against the file's text. A `CREATE TABLE` that SQLite would reject, or a trigger
naming a column that is not there, is invisible to any amount of reading.
"""

from __future__ import annotations

import pathlib
import sqlite3
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "db" / "engine" / "schema.sql"
DERIVE = ROOT / "tools" / "derive_engine_schema.py"

#: Defined in both streams, identically, and correct to have once. Everything
#: else appearing twice is a real collision and the tool refuses it.
SHARED = {("table", "database_migration"), ("table", "scrapex_meta")}


def _built(sql: str, tmp_path, name: str) -> sqlite3.Connection:
    con = sqlite3.connect(tmp_path / name)
    con.executescript(sql)
    return con


def _objects(con) -> dict[tuple[str, str], str]:
    return {(t, n): s for t, n, s in con.execute(
        "SELECT type, name, sql FROM sqlite_master WHERE sql IS NOT NULL")}


def _columns(con, table: str) -> dict[str, tuple]:
    return {r[1]: (r[2], r[3], r[5]) for r in con.execute(f'PRAGMA table_info("{table}")')}


@pytest.fixture(scope="module")
def streams(tmp_path_factory):
    """The two databases as they are today, built by their own migrations."""
    from scrapex.databases.domain import GeneralDatabase, MarketLensDatabase

    out = {}
    base = tmp_path_factory.mktemp("streams")
    for cls, name in ((MarketLensDatabase, "marketlens"), (GeneralDatabase, "general")):
        path = base / f"{name}.db"
        cls(path).initialize()
        out[name] = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    return out


@pytest.fixture(scope="module")
def engine_schema(tmp_path_factory):
    """A database built from the committed file, which is the thing under test."""
    con = sqlite3.connect(tmp_path_factory.mktemp("engine") / "engine.db")
    con.executescript(SCHEMA.read_text(encoding="utf-8"))
    return con


def test_the_committed_schema_is_what_the_streams_derive_to():
    """THE GUARD THAT KEEPS THE OTHERS HONEST. A generated file that nothing
    re-derives is a snapshot of a moment, and it stops being true the first time
    a migration lands."""
    done = subprocess.run([sys.executable, str(DERIVE), "--check"],
                          cwd=ROOT, capture_output=True, text=True)
    assert done.returncode == 0, (
        f"{done.stdout}{done.stderr}\n"
        "db/engine/schema.sql no longer matches the streams it was derived from")


def test_it_is_a_schema_sqlite_will_actually_accept(engine_schema):
    """Reading SQL proves nothing about whether it runs. This file is executed
    into a real database before anything else is asserted about it."""
    tables = [n for t, n in _objects(engine_schema) if t == "table"]
    assert len(tables) > 40, f"only {len(tables)} tables were created"


def test_every_object_from_both_streams_survives(engine_schema, streams):
    """Tables, indexes, triggers and views — by name, from both sides.

    A trigger is the one most easily lost and the most expensive to lose: the
    generic stream carries sixteen of them, and several are what make an
    append-only log append-only. Dropping one turns a guarantee into a comment.
    """
    have = set(_objects(engine_schema))
    for name, con in streams.items():
        missing = sorted(set(_objects(con)) - have)
        assert not missing, f"the {name} stream's {missing} are not in the one schema"


def test_every_column_of_every_table_survives(engine_schema, streams):
    """A TABLE THAT IS PRESENT CAN STILL BE WRONG, and the name check above
    would pass it. Type, NOT NULL and DEFAULT are compared too, because a
    column that lost its default writes NULL where the old one wrote a value —
    which is not an error anywhere, just wrong data from then on."""
    for name, con in streams.items():
        for typ, table in sorted(_objects(con)):
            if typ != "table":
                continue
            was, now = _columns(con, table), _columns(engine_schema, table)
            missing = sorted(set(was) - set(now))
            assert not missing, f"{name}.{table} lost columns {missing}"
            changed = sorted(c for c in was if was[c] != now[c])
            assert not changed, (
                f"{name}.{table} columns {changed} changed shape: "
                + ", ".join(f"{c}: {was[c]} -> {now[c]}" for c in changed))


def test_the_two_streams_only_overlap_where_they_are_allowed_to(streams):
    """The union is only safe because they barely touch. If a third name ever
    appears in both, merging silently picks a winner — so this fails first and
    names it."""
    price, generic = _objects(streams["marketlens"]), _objects(streams["general"])
    overlap = set(price) & set(generic)

    assert overlap == SHARED, (
        f"the streams now share {sorted(overlap - SHARED)}, which the derivation "
        "would merge by letting one silently win")
    for key in overlap:
        assert price[key].strip() == generic[key].strip(), (
            f"{key[1]} is spelled differently in the two streams")


def test_the_generic_tables_the_plan_names_are_all_here(engine_schema):
    """PLATFORM-PLAN M5: "bring the eleven generic tables in beside the priced
    offers". Named individually rather than counted, because a count is
    satisfied by any eleven tables."""
    have = {n for t, n in _objects(engine_schema) if t == "table"}
    for table in ("generic_page_snapshot", "generic_record", "generic_record_revision",
                  "generic_ingestion", "dataset_definition", "dataset_schema_version",
                  "schema_version_field", "field_definition", "dataset_relationship",
                  "relationship_field_pair", "site_profile"):
        assert table in have, f"{table} did not survive the collapse"


def test_the_priced_offers_are_still_there(engine_schema):
    """The other half of M5's "done when": every existing price test still
    passes. This is the shape those tests need before any of them can run."""
    have = {n for t, n in _objects(engine_schema) if t == "table"}
    for table in ("price_observation", "source_offer", "offer_state",
                  "source_product", "source_product_attribute", "crawl_run"):
        assert table in have, f"{table} did not survive the collapse"
