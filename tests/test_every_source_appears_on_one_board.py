"""Every source, in one list, whichever registry it lives in.

WHY THIS FILE EXISTS. He asked «اى الجديد واى الى خلص» — which is new and which is
finished — and measured 2026-08-21 **no command could answer it**: eighteen
subcommands and not one listed the sources. `R-32` settles that price is one
**category** among several; `REQ-25` is the single registry. `sourceboard` is the
read-only view that answers the question *before* the merge, so the merge stays a
decision on its own merits rather than something a missing report forces.

THE THREE THINGS THAT MUST NOT DRIFT, and each has a test below:

  * IT WORKS WITH NO DATABASE. A new installation has none — `R-23` calls that the
    normal first run — and a report that needs data before it can list what would
    produce data is a report a new user cannot use.
  * "REGISTERED" MEANS NO COLLECTOR, and only `family: TBD-probe` can say it. That is
    his «يحفظ فقط فى قائمة مصادر حتى ياتى دوره», and `SourceEntry` validation refuses
    to let such a source go active.
  * THE TWO REGISTRIES STAY VISIBLE. The `registry` column is not decoration: it is
    the split `REQ-25` exists to remove, and smoothing it over in the output would
    hide the very thing that needs fixing.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from scrapex import sourceboard
from scrapex.databases import DatabaseRegistry, EngineDatabase
from scrapex.vocab import SourceCategory

MANIFEST = Path(__file__).resolve().parent.parent / "sources.yaml"


@pytest.fixture()
def conn(tmp_path: Path):
    registry = DatabaseRegistry(EngineDatabase(tmp_path / "scrapex-engine.db"),
                                pointer_file=tmp_path / "databases.json")
    registry.initialize()
    connection = registry.engine.connect()
    try:
        yield connection
    finally:
        connection.close()


def site(conn, key: str, *, lifecycle: str = "active",
         scope: str = "listing_only") -> None:
    conn.execute(
        "INSERT INTO source_site (source_key, source_name, base_url, crawl_scope, "
        "  lifecycle) VALUES (?,?,?,?,?)",
        (key, key.title(), f"https://{key}.test/", scope, lifecycle))
    conn.commit()


# ---- it works before there is anything to report ----------------------------

def test_the_board_reads_without_a_database(conn):
    """`conn=None` is the new user's first run, and the products half is a file."""
    found = sourceboard.board(None, manifest_file=MANIFEST)

    assert found, "the manifest's own sources should be listed with no warehouse"
    assert {one.registry for one in found} == {"manifest"}


def test_a_warehouse_adds_to_the_list_rather_than_replacing_it(conn):
    """Both registries, one list — which is the whole point of the module."""
    before = sourceboard.board(None, manifest_file=MANIFEST)
    site(conn, "muqawil_org")

    after = sourceboard.board(conn, manifest_file=MANIFEST)

    assert len(after) == len(before) + 1
    assert {one.registry for one in after} == {"manifest", "warehouse"}


# ---- the state vocabulary ---------------------------------------------------

def test_every_state_is_one_of_the_four_words(conn):
    """A fifth spelling appearing anywhere means the two registries drifted again."""
    site(conn, "muqawil_org")

    for one in sourceboard.board(conn, manifest_file=MANIFEST):
        assert one.state in sourceboard.STATES, one


def test_a_source_with_no_collector_reads_as_registered(tmp_path):
    """`family: TBD-probe` is the only way any registry can say "waiting its turn".

    Written against a manifest of its own rather than `sources.yaml`, because
    nothing in the real one is TBD-probe today — the mechanism is real and currently
    empty, and a test that asserts on today's data would break the day he adds one.
    """
    manifest = tmp_path / "sources.yaml"
    # Every REQUIRED field, read off `SourceEntry.model_fields` rather than guessed:
    # source_key, source_name, base_url, family, extract. A fixture missing one is
    # refused by pydantic, which is the loud version of the failure that has cost
    # this repository hours in its silent version -- see LESSONS.md on
    # `INSERT OR IGNORE`.
    manifest.write_text(
        "sources:\n"
        "  - source_key: NEWTHING\n"
        "    source_name: A source he has given us\n"
        "    base_url: https://newthing.test/\n"
        "    family: TBD-probe\n"
        "    active: false\n"
        "    extract:\n"
        "      - kind: product_prices\n"
        "        scope: targeted\n", encoding="utf-8")

    found = sourceboard.board(None, manifest_file=manifest)

    assert [(one.key, one.state) for one in found] == [("NEWTHING", "registered")]


def test_a_paused_site_is_not_reported_as_built(conn):
    """`paused` is a decision someone took; `built` is a state a source is in.
    Collapsing them would report a deliberately stopped source as merely idle."""
    site(conn, "stopped_org", lifecycle="paused")

    found = {one.key: one.state
             for one in sourceboard.board(conn, manifest_file=MANIFEST)}

    assert found["stopped_org"] == "paused"


# ---- categories -------------------------------------------------------------

def test_the_manifest_is_products_and_the_warehouse_is_contractors(conn):
    """His two categories, and where each currently lives."""
    site(conn, "muqawil_org")

    by_registry = {}
    for one in sourceboard.board(conn, manifest_file=MANIFEST):
        by_registry.setdefault(one.registry, set()).add(one.category)

    assert by_registry["manifest"] == {SourceCategory.PRODUCTS}
    assert by_registry["warehouse"] == {SourceCategory.CONTRACTORS}


def test_filtering_by_category_returns_only_that_category(conn):
    site(conn, "muqawil_org")

    found = sourceboard.board(conn, manifest_file=MANIFEST,
                              category=SourceCategory.CONTRACTORS)

    assert [one.key for one in found] == ["muqawil_org"]


def test_the_summary_counts_by_category_and_state(conn):
    """His question reduced to a number per cell."""
    site(conn, "muqawil_org")

    counted = sourceboard.summary(
        sourceboard.board(conn, manifest_file=MANIFEST))

    assert counted["contractors"] == {"active": 1}
    assert sum(counted["products"].values()) == len(
        sourceboard.board(None, manifest_file=MANIFEST))


# ---- the split stays visible ------------------------------------------------

def test_a_retired_source_site_is_not_listed(conn):
    """`valid_to` is how the generic side retires a row, and a retired source is
    not a source this installation has."""
    site(conn, "gone_org")
    conn.execute("UPDATE source_site SET valid_to = '2026-01-01T00:00:00Z' "
                 " WHERE source_key = 'gone_org'")
    conn.commit()

    assert "gone_org" not in {
        one.key for one in sourceboard.board(conn, manifest_file=MANIFEST)}


def test_the_registry_each_source_came_from_is_reported(conn):
    """Not decoration: it is the two-registry split `REQ-25` exists to remove, and
    hiding it in the output would hide the thing that needs fixing."""
    site(conn, "muqawil_org")

    line = next(str(one) for one in sourceboard.board(conn, manifest_file=MANIFEST)
                if one.key == "muqawil_org")

    assert "warehouse" in line
