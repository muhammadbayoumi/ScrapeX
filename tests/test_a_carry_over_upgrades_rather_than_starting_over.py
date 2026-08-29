"""A user's data survives the schema evolving. That is the promise, not a nicety.

THE OWNER'S RULING, 2026-08-20, after I created an empty database beside his full
one instead of upgrading it:

    «الافضل تطويرها لان عند نشر الاداة المفروض نحافظ على بيانات المستخدمين وقاعدة
     البيانات تتطور ويظل بياناتهم محفوظة»

So `carry_over` is not a convenience command — it is the **upgrade path of a
shipped product**, and every installation that predates the collapse goes through
it exactly once. It had never been run against a real pre-0058 installation, and
the first time it was, it aborted:

    error: a selling unit must carry its provenance and its witness

Migration 0058 added two columns to `source_offer` and two triggers that refuse a
row carrying a `selling_unit_id` without them. 261 of the owner's 3,739 offers
carry one; the old schema has no such columns. So the carry-over was closed for
precisely the installations it exists for, and nothing had noticed because no test
ever carried a table whose new schema demanded a column the old one lacked.

WHY THE VALUE IS NOT INVENTED HERE, which is the only thing that would make this
unacceptable. 0058 met these same rows in the in-place path and already answered:
`legacy_unwitnessed`, with a witness that says in words that nobody can say where
the value came from. `test_the_legacy_marker_is_the_migrations_own_and_not_a_copy`
is what keeps the two from drifting — a second literal that silently disagrees
with the first would let a carried installation and an upgraded one describe the
same row differently.
"""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import pytest

from scrapex.databases.carry_over import (
    BACKFILLS,
    LEGACY_UNWITNESSED,
    LEGACY_WITNESS,
    CarryOverPlan,
    carry_over,
)

ROOT = Path(__file__).resolve().parents[1]

#: The shape of the old, split-era price database, cut down to what this is about:
#: `source_offer` as it was before 0058, with no provenance columns at all.
OLD_SCHEMA = """
CREATE TABLE selling_unit (
    selling_unit_id INTEGER PRIMARY KEY,
    unit_code       TEXT NOT NULL UNIQUE,
    name_ar         TEXT,
    name            TEXT
);
CREATE TABLE source_site (
    source_id INTEGER PRIMARY KEY,
    source_key TEXT NOT NULL UNIQUE,
    base_url TEXT NOT NULL DEFAULT '',
    display_name TEXT NOT NULL DEFAULT ''
);
CREATE TABLE source_product (
    source_product_id   INTEGER PRIMARY KEY,
    source_id           INTEGER NOT NULL,
    external_product_id TEXT NOT NULL
);
CREATE TABLE source_variant (
    source_variant_id INTEGER PRIMARY KEY,
    source_product_id INTEGER NOT NULL,
    external_variant_id TEXT
);
CREATE TABLE source_offer (
    offer_id             INTEGER PRIMARY KEY,
    source_variant_id    INTEGER,
    branch_id            INTEGER,
    country_code_alpha2  TEXT,
    customer_segment     TEXT,
    selling_unit_id      INTEGER REFERENCES selling_unit(selling_unit_id),
    basis_quantity       REAL,
    minimum_quantity     REAL,
    currency             TEXT,
    tax_included         INTEGER,
    quantity_increment   REAL,
    quantity_is_decimal  INTEGER,
    weight               REAL,
    weight_unit          TEXT
);
"""


def _old_database(path: Path, *, offers_with_a_unit: int,
                  offers_without: int) -> None:
    """A pre-0058 price database with real rows in it."""
    conn = sqlite3.connect(path)
    conn.executescript(OLD_SCHEMA)
    conn.execute("INSERT INTO selling_unit (selling_unit_id, unit_code) "
                 "VALUES (1, 'kg')")
    conn.execute("INSERT INTO source_product (source_product_id, source_id, "
                 " external_product_id) VALUES (1, 1, 'p1')")
    conn.execute("INSERT INTO source_variant (source_variant_id, "
                 " source_product_id) VALUES (1, 1)")
    # EVERY COLUMN THE NEW SCHEMA CALLS `NOT NULL` IS POPULATED, and this cost two
    # rounds to get right. The copy names every shared column explicitly, so an old
    # NULL is passed as NULL and the new schema's DEFAULT never applies — the row is
    # rejected, and `INSERT OR IGNORE` drops it in silence exactly as OP-17 warns.
    # The first draft left six of these NULL, all 3,739 rows were dropped, and the
    # test reported `written: 0` with no error whatsoever.
    #
    # It is a FIXTURE fault and not a defect, and that was measured rather than
    # assumed: the owner's real `source_offer` has **0 NULLs of 3,739** in every one
    # of `country_code_alpha2`, `customer_segment`, `basis_quantity`,
    # `quantity_is_decimal`, `tax_included` and `source_variant_id`. A fixture built
    # from memory was describing data that does not exist.
    # AND EVERY ROW IS DISTINCT UNDER `ux_source_offer_identity`, which is
    # `(source_variant_id, COALESCE(branch_id,''), country_code_alpha2,
    # customer_segment, COALESCE(selling_unit_id,0), basis_quantity)`. The second
    # draft of this fixture made 3,739 rows identical apart from the primary key, so
    # the unique index collapsed them and exactly ONE arrived — `INSERT OR IGNORE`
    # again reporting nothing. `branch_id` is what varies here, because it is the
    # one identity field a real installation genuinely varies per branch.
    columns = ("offer_id, source_variant_id, selling_unit_id, basis_quantity, "
               "currency, tax_included, country_code_alpha2, customer_segment, "
               "quantity_is_decimal, branch_id")
    offer = 1
    for _ in range(offers_with_a_unit):
        conn.execute(
            f"INSERT INTO source_offer ({columns}) "
            "VALUES (?, 1, 1, 1.0, 'SAR', 0, 'SA', 'retail', 0, ?)",
            (offer, f"b{offer}"))
        offer += 1
    for _ in range(offers_without):
        conn.execute(
            f"INSERT INTO source_offer ({columns}) "
            "VALUES (?, 1, NULL, 1.0, 'SAR', 0, 'SA', 'retail', 0, ?)",
            (offer, f"b{offer}"))
        offer += 1
    # The pointer's `user_version` is the OLD stream's, which is exactly why the
    # file cannot simply be migrated forward — measured 2026-08-20: the engine
    # refuses it on `application_id` before it even reads the version.
    conn.execute("PRAGMA user_version = 55")
    conn.commit()
    conn.close()


@pytest.fixture()
def plan(tmp_path: Path) -> CarryOverPlan:
    old = tmp_path / "marketlens.db"
    _old_database(old, offers_with_a_unit=261, offers_without=3478)
    return CarryOverPlan(marketlens=old, general=None,
                         destination=tmp_path / "engine" / "scrapex-engine.db",
                         pointer=tmp_path / "databases.json")


# ---- the defect itself -------------------------------------------------------

def test_a_pre_0058_installation_carries_over_at_all(plan: CarryOverPlan):
    """THE WHOLE DEFECT IN ONE ASSERTION. Before the fix this raised
    `sqlite3.IntegrityError: a selling unit must carry its provenance and its
    witness`, the pointer never moved, and the owner's 3,739 offers stayed behind
    a pointer nothing would open."""
    report = carry_over(plan)

    assert report["ok"], report.get("short")
    assert report["tables"]["source_offer"]["written"] == 3739
    assert report.get("pointer_moved_to") == str(plan.destination)


def test_every_offer_that_had_a_unit_arrives_marked_legacy(plan: CarryOverPlan):
    """The 261 rows the trigger was refusing arrive, and arrive SAYING they are
    unwitnessed rather than claiming a provenance nobody can support."""
    carry_over(plan)

    conn = sqlite3.connect(plan.destination)
    marked = conn.execute(
        "SELECT COUNT(*) FROM source_offer WHERE unit_basis_provenance = ?",
        (LEGACY_UNWITNESSED,)).fetchone()[0]
    witnessed = conn.execute(
        "SELECT COUNT(*) FROM source_offer WHERE unit_basis_witness = ?",
        (LEGACY_WITNESS,)).fetchone()[0]
    conn.close()

    assert marked == 261
    assert witnessed == 261


def test_an_offer_with_no_unit_is_left_alone(plan: CarryOverPlan):
    """0058's own `UPDATE` is `WHERE selling_unit_id IS NOT NULL`, and this must
    match it. An offer with no unit has nothing to state the provenance OF, and
    filling it would claim a fact about 3,478 rows the migration deliberately
    leaves untouched — and would make the resolution metric read better than the
    data."""
    carry_over(plan)

    conn = sqlite3.connect(plan.destination)
    stray = conn.execute(
        "SELECT COUNT(*) FROM source_offer "
        " WHERE selling_unit_id IS NULL AND unit_basis_provenance IS NOT NULL"
    ).fetchone()[0]
    untouched = conn.execute(
        "SELECT COUNT(*) FROM source_offer "
        " WHERE selling_unit_id IS NULL AND unit_basis_provenance IS NULL"
    ).fetchone()[0]
    conn.close()

    assert stray == 0
    assert untouched == 3478


def test_the_carry_over_says_which_columns_it_filled(plan: CarryOverPlan):
    """A value this command supplied is not a value the user's data contained, so
    it is REPORTED. An unreported fill is indistinguishable from data that was
    always there — which is the thing this project refuses to let happen to source
    truth."""
    report = carry_over(plan)

    filled = report.get("backfilled") or []
    assert [entry["table"] for entry in filled] == ["source_offer"]
    assert sorted(filled[0]["columns"]) == [
        "unit_basis_provenance", "unit_basis_witness"]
    assert filled[0]["rows"] == 261
    assert "migration 0058" in filled[0]["why"]


# ---- the literal must not become a second source of truth --------------------

# `test_migration_00NN_*` REMOVED 2026-08-29 WITH THE MIGRATION IT GUARDED.
# `db/migrations/` was retired on his ruling; a test that replays a stream by
# number to reach a file that no longer exists cannot fail for a real reason, and
# keeping it is the doubled effort the retirement was for.
# The migration itself is still readable: `git show 8901a2a:db/migrations/`.


def test_a_backfill_never_overwrites_a_column_the_source_already_had():
    """A source that carries the column carries its VALUES too, and replacing real
    provenance with a legacy marker is the exact inversion of the point. Asserted
    on the selector rather than through a carry-over, because the case it guards is
    a FUTURE source schema that already has the column."""
    from scrapex.databases.carry_over import _backfill_for

    target = ["offer_id", "selling_unit_id", "unit_basis_provenance",
              "unit_basis_witness"]
    assert _backfill_for("source_offer", ["offer_id", "selling_unit_id"],
                         target) is not None
    assert _backfill_for(
        "source_offer",
        ["offer_id", "selling_unit_id", "unit_basis_provenance",
         "unit_basis_witness"],
        target) is None, "the source already had both; nothing to fill"
    assert _backfill_for("price_observation", ["offer_id"], target) is None


def test_the_backfill_registry_names_a_gate_column_it_can_actually_read():
    """Each backfill is conditional on a column, and that column must exist in the
    OLD schema or the condition can never be evaluated — the fill would then either
    crash or silently apply to everything."""
    for backfill in BACKFILLS:
        assert backfill.when in OLD_SCHEMA or backfill.table != "source_offer", (
            f"{backfill.table}.{backfill.when} is the gate for this backfill and "
            "the pre-0058 fixture does not have it")
        assert backfill.values, "a backfill that fills nothing is not a backfill"
