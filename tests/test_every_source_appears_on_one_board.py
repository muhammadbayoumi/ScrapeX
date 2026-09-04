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
    """`conn=None` is the new user's first run, and NEITHER half needs a database.

    THE CODE REGISTRY IS THE HALF HE ASKED FOR — *«المفروض المصادر تظهر بدون بيانات فهى
    مسجلة ومحفوظة فى الكود»*. A directory this build can crawl is a fact about the
    build, so it is listed before any warehouse exists, exactly as the manifest is.
    """
    found = sourceboard.board(None, manifest_file=MANIFEST)

    assert found, "the manifest's own sources should be listed with no warehouse"
    assert {one.registry for one in found} == {"manifest", "code"}
    assert [one.key for one in found if one.registry == "code"] == ["muqawil_org"]


def test_a_warehouse_adds_to_the_list_rather_than_replacing_it(conn):
    """Every registry, one list — which is the whole point of the module.

    IT USED TO ADD `muqawil_org` AND THAT STOPPED BEING AN ADDITION. The code registry
    lists that key before any crawl, so inserting it now REPLACES rather than adds —
    which is the next test. A key the code does not register is what still measures
    addition.
    """
    before = sourceboard.board(None, manifest_file=MANIFEST)
    site(conn, "some_other_directory")

    after = sourceboard.board(conn, manifest_file=MANIFEST)

    assert len(after) == len(before) + 1
    assert {one.registry for one in after} == {"manifest", "warehouse", "code"}


def test_a_crawled_directory_is_listed_once_by_the_warehouse_and_not_twice(conn):
    """`REQ-37` and `R-47` in the list instead of on the screen.

    Once a directory has been crawled it has a `source_site` row carrying its real
    lifecycle and dataset count. The code registry's entry for the same key must step
    aside: two rows for one source is the twice-drawn card he complained about, and a
    board that reported it would send the panel the same defect.
    """
    site(conn, "muqawil_org", lifecycle="paused")

    found = [one for one in sourceboard.board(conn, manifest_file=MANIFEST)
             if one.key == "muqawil_org"]

    assert len(found) == 1, [(one.registry, one.state) for one in found]
    assert found[0].registry == "warehouse", "the placeholder beat the real row"
    assert found[0].state == "paused", (
        "the code registry's `built` overwrote a decision someone took")


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

    # THE MANIFEST HALF, NAMED. This asserted on the whole board, which measured the
    # manifest only while the manifest was the only registry that needs no database.
    # `registered` still comes from exactly one place and this still proves it.
    from_manifest = [(one.key, one.state) for one in found
                     if one.registry == "manifest"]
    assert from_manifest == [("NEWTHING", "registered")]
    assert not [one for one in found
                if one.state == "registered" and one.registry != "manifest"], (
        "a second registry started claiming `registered`, which only the manifest can "
        "say: a source on the list with no collector at all")


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

    assert counted["contractors"] == {"active": 1}, (
        "the crawled row and the code registry's placeholder were both counted")
    # THE PRODUCTS CELL IS THE MANIFEST, and it used to be compared against the whole
    # database-less board — which was the same number only while the manifest was the
    # only registry that needs no database. `from_manifest` names what it means.
    assert sum(counted["products"].values()) == len(
        sourceboard.from_manifest(MANIFEST))


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
