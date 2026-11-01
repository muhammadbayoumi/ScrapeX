"""An offer the source stopped stating leaves his table, and comes back if it returns.

An offer's identity holds its country and its unit, so a reading that changes either
lands on another offer, and nothing told the old one (#1874). On his warehouse
(v26, 2026-10-31) that left three shapes, and each is a test here:

- SPARK_ESHOP: 3,149 offers at country `*` and currency UNKNOWN beside their `EG`
  twins. The table drew 6,331 rows for 3,182 variants.
- MADAR: three cartons with a legacy `kg` 12.5 beside a unit-less re-read, at prices
  last confirmed in August or September.
- MADAR: six nail boxes whose crawl of 2026-10-25 read `kg` again and landed on the
  retired `kg` offer, which every read path hides, so his table kept the `box` sibling's
  figure: 22.94 where the shop said 16.80.

What must NOT retire is as much the point: GPP_ENERGY's countries, and a variant a run
did not mention.
"""
from __future__ import annotations

import sqlite3

import pytest

from scrapex import db as dbmod
from scrapex.config import MANIFEST_FILE, ExtractSpec, SourceEntry
from scrapex.connectors.base import ScrapedTable
from scrapex.ingest import ingest_payloads
from scrapex.payload import PAYLOAD_VERSION, FunnelPayload
from scrapex.reports import browse_observations, price_extremes
from scrapex.rowspec import COMMODITY_PRICE, PRODUCT_PRICES, RowBuilder
from scrapex.vocab import ExtractKind, ExtractScope

_WITNESS = {"selling_unit_raw": "4 كجم", "selling_unit_raw_lang": "ar",
            "unit_basis_provenance": "stated_field",
            "unit_basis_witness": "variant_axes_ar@ar/v1: 4 كجم"}


@pytest.fixture()
def conn() -> sqlite3.Connection:
    c = dbmod.connect(":memory:")
    dbmod.migrate(c)
    yield c
    c.close()


def entry() -> SourceEntry:
    return SourceEntry.model_validate(dict(
        source_key="SHOP", source_name="Shop", base_url="https://shop.example",
        family="shopify-json", currency="SAR", default_region="*", vat_mode="incl",
        extract=[ExtractSpec(kind=ExtractKind.PRODUCT_PRICES, scope=ExtractScope.CENSUS)]))


def row(**over) -> list[str]:
    fields = dict(
        external_product_id="1", external_variant_id="11", external_sku="S1",
        product_name="Wood nails", country_code_alpha2="SA", currency="SAR",
        tax_included="1", price="16.80", availability="in_stock")
    fields.update(over)
    return RowBuilder(PRODUCT_PRICES).row(**fields)


def kg(**over) -> list[str]:
    return row(unit="kg", basis_quantity="4", **_WITNESS, **over)


def box(**over) -> list[str]:
    return row(unit="box", basis_quantity="1", content_quantity="4", content_unit="kg",
               selling_unit_raw="4 كجم/صندوق", selling_unit_raw_lang="ar",
               unit_basis_provenance="stated_field",
               unit_basis_witness="variant_axes_ar@ar/v1: 4 كجم/صندوق", **over)


def crawl(conn, rows, day: int = 1):
    return ingest_payloads(conn, entry(), [FunnelPayload(
        payload_version=PAYLOAD_VERSION, source_key="SHOP",
        kind=ExtractKind.PRODUCT_PRICES, client="cli",
        scraped_at=f"2026-10-{day:02d}T10:00:00Z",
        source_url="https://shop.example/p", header=list(PRODUCT_PRICES.columns), rows=rows)])


def offers(conn) -> list[tuple]:
    return [tuple(r) for r in conn.execute(
        "SELECT o.offer_id, su.unit_code, o.basis_quantity, o.country_code_alpha2, o.status "
        "FROM source_offer o LEFT JOIN selling_unit su USING (selling_unit_id) "
        "ORDER BY o.offer_id")]


def active(conn) -> list[tuple]:
    """Unit, basis and country of what the read paths show."""
    return [(unit, basis, country) for _id, unit, basis, country, status in offers(conn)
            if status == "active"]


def table(conn) -> list[tuple]:
    return [(r["unit"], r["price"]) for r in browse_observations(conn, "SHOP").rows]


# ---- the three shapes on his warehouse --------------------------------------

def test_a_named_country_answers_for_the_unknown_one_and_the_history_stays(conn):
    """SPARK_ESHOP: `*` / UNKNOWN from 2026-08-03, `EG` / EGP ever since."""
    crawl(conn, [row(country_code_alpha2="*", currency="UNKNOWN")], day=1)
    old_id = offers(conn)[0][0]

    result = crawl(conn, [row(country_code_alpha2="EG", currency="EGP")], day=2)

    assert active(conn) == [(None, 1.0, "EG")], "the variant still drew two rows"
    assert len(table(conn)) == 1
    assert conn.execute("SELECT COUNT(*) FROM price_observation WHERE offer_id = ?",
                        (old_id,)).fetchone()[0] == 1, "retiring an offer lost its history"
    assert any("retired 1 offer" in notice for notice in result.notices), (
        "a change to what his table shows happened with no line in the job's log")
    assert result.status.value == "success", "a retirement is housekeeping, not an error"
    assert [row["country_code_alpha2"] for row in price_extremes(conn, "SHOP")] == ["EG"], (
        "the Changes page still shows a retired offer as current")


def test_the_changes_page_lists_only_what_is_current(tmp_path):
    """The panel opens this page, and it picks a timeline from offers with a story. A
    retired offer is not offered once it retires, and is again once it comes back."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from scrapex.webui.app import create_app

    path = tmp_path / "w.db"
    conn = dbmod.connect(path)
    dbmod.migrate(conn)
    crawl(conn, [kg(price="10.00")], day=1)
    crawl(conn, [kg(price="12.00")], day=2)
    the_kg = offers(conn)[0][0]
    conn.commit()
    client = TestClient(create_app(path, manifest_path=MANIFEST_FILE))
    option = f'<option value="{the_kg}">'

    assert option in client.get("/changes", params={"source_key": "SHOP"}).text

    crawl(conn, [box(price="12.00")], day=3)
    conn.commit()
    assert option not in client.get("/changes", params={"source_key": "SHOP"}).text, (
        "a retired offer is still offered as a current timeline")

    crawl(conn, [kg(price="14.00")], day=4)
    conn.commit()
    assert option in client.get("/changes", params={"source_key": "SHOP"}).text
    conn.close()


def test_the_existing_pair_clears_on_the_next_crawl(conn):
    """The 3,149 already stand beside their twins, so the twin is `found`, not minted:
    a rule that only fired when minting would leave every one of them."""
    crawl(conn, [row(country_code_alpha2="EG", currency="EGP")], day=1)
    conn.execute(
        "INSERT INTO source_offer (source_variant_id, country_code_alpha2, currency, "
        " tax_included) SELECT source_variant_id, '*', 'UNKNOWN', 1 FROM source_variant")
    assert len(active(conn)) == 2

    crawl(conn, [row(country_code_alpha2="EG", currency="EGP")], day=2)

    assert active(conn) == [(None, 1.0, "EG")]


def test_a_legacy_unit_beside_a_unit_less_re_read_retires(conn):
    """MADAR's three cartons: the state exists on his warehouse, built here as it stands
    there, and the next crawl restating the unit-less offer retires the old one."""
    crawl(conn, [row()], day=1)
    conn.execute("INSERT OR IGNORE INTO selling_unit (unit_code) VALUES ('kg')")
    conn.execute(
        "INSERT INTO source_offer (source_variant_id, country_code_alpha2, currency, "
        " tax_included, selling_unit_id, basis_quantity, unit_basis_provenance, "
        " unit_basis_witness) "
        "SELECT source_variant_id, 'SA', 'SAR', 1, "
        "       (SELECT selling_unit_id FROM selling_unit WHERE unit_code = 'kg'), 12.5, "
        "       'legacy_unwitnessed', 'written without a charter' FROM source_variant")
    assert len(active(conn)) == 2

    crawl(conn, [row()], day=2)

    assert active(conn) == [(None, 1.0, "SA")]


def test_a_reading_that_lands_on_a_retired_offer_shows_its_price(conn):
    """MADAR's six boxes, end to end. The shop moved kg -> box -> kg, and on the way back
    his table showed the box's old price because the new one landed out of sight."""
    crawl(conn, [kg(price="15.00")], day=1)
    crawl(conn, [box(price="22.94")], day=2)
    assert active(conn) == [("box", 1.0, "SA")]

    result = crawl(conn, [kg(price="16.80")], day=3)

    assert active(conn) == [("kg", 4.0, "SA")], "the crawl landed on a hidden offer"
    shown = table(conn)
    assert len(shown) == 1
    assert shown[0][1] == 16.80, f"his table shows {shown[0][1]}, the shop said 16.80"
    assert any("1 retired offer(s) are stated again" in notice for notice in result.notices), (
        "six figures on his table changed by revival with no line in the job's log")


def test_a_unit_stated_again_after_the_offer_went_blank_and_retired_is_shown(conn):
    """The same defect through the other door. The box goes blank when the shop stops
    stating it, the run stating `kg` retires the blank offer, and then the shop says box
    again: the learning path must bring that series back, not write its price out of sight."""
    crawl(conn, [kg(price="15.00")], day=1)
    crawl(conn, [box(price="22.94")], day=2)
    the_box = next(o[0] for o in offers(conn) if o[4] == "active")
    crawl(conn, [row(price="22.94")], day=3)
    crawl(conn, [kg(price="16.80")], day=4)

    result = crawl(conn, [box(price="30.00")], day=5)

    assert table(conn) == [("box", 30.00)], "his table shows an old figure"
    assert [o[0] for o in offers(conn) if o[4] == "active"] == [the_box], (
        "the box's price series was not continued")
    assert any("1 retired offer(s) are stated again" in notice for notice in result.notices)


def test_the_live_blank_offer_learns_the_unit_before_a_retired_one(conn):
    """Two unit-less offers can stand on one variant when their bases differ, and the sweep
    retires the one the run did not restate. The series that continues is the live one."""
    crawl(conn, [row(basis_quantity="2")], day=1)
    retired = offers(conn)[0][0]
    crawl(conn, [row()], day=2)
    live = next(o[0] for o in offers(conn) if o[4] == "active")
    assert live != retired

    crawl(conn, [kg()], day=3)

    assert [o[0] for o in offers(conn) if o[4] == "active"] == [live], (
        "a retired offer took the unit while a live one stood")


def test_a_new_unit_lands_on_the_retired_blank_offer_when_no_other_stands(conn):
    """MADAR's cartons after the next crawl, and then a unit they have never held."""
    crawl(conn, [row()], day=1)
    crawl(conn, [kg(price="12.00")], day=2)
    crawl(conn, [row(price="12.00")], day=3)
    crawl(conn, [box(price="99.00")], day=4)

    assert table(conn) == [("box", 99.00)]
    assert sum(1 for o in offers(conn) if o[4] == "active") == 1


# ---- a unit that goes away --------------------------------------------------

def test_a_lost_unit_stays_the_same_offer_with_its_history(conn):
    """#1873's fix and any shop edit go through here. A new offer would start his price
    history over and leave the old one beside it."""
    crawl(conn, [kg()], day=1)
    offer_id = offers(conn)[0][0]

    result = crawl(conn, [row()], day=2)

    assert [o[0] for o in offers(conn)] == [offer_id], "losing the unit minted a second offer"
    assert any("1 offer(s) no longer state a unit" in notice for notice in result.notices), (
        "a unit went blank on his table with no line in the job's log")
    stored = conn.execute(
        "SELECT selling_unit_id, basis_quantity, selling_unit_raw, selling_unit_raw_lang, "
        "unit_basis_provenance, unit_basis_witness, content_quantity, content_unit_id, status "
        "FROM source_offer").fetchone()
    assert tuple(stored) == (None, 1.0, None, None, None, None, None, None, "active"), (
        "a blank unit kept a fact from the reading it replaced")
    assert table(conn)[0][0] == ""


def test_losing_a_unit_at_the_same_price_is_not_a_price_change(conn):
    """The unit is in the price key (pricekey.IDENTITY_FIELDS), so a new period opens, the
    same as when an offer learns its unit. What it must not do is tell him the price moved."""
    crawl(conn, [kg()], day=1)
    crawl(conn, [row()], day=2)

    assert conn.execute(
        "SELECT COUNT(*) FROM change_event WHERE change_type IN "
        "('price_increase', 'price_decrease')").fetchone()[0] == 0, (
        "a unit going blank was reported as a price change")
    assert table(conn)[0][1] == 16.80


def test_the_lost_unit_path_still_takes_the_rows_quantity_facts(conn):
    """4,437 of MADAR's 4,442 unit-less offers state a minimum, so such a row states one."""
    crawl(conn, [kg(minimum_quantity="5")], day=1)
    crawl(conn, [row(minimum_quantity="10")], day=2)

    assert conn.execute("SELECT minimum_quantity FROM source_offer").fetchone()[0] == 10.0


def test_a_quiet_crawl_says_nothing(conn):
    """Nothing moved, so nothing is announced, on the second identical crawl of each kind."""
    crawl(conn, [kg()], day=1)
    assert not crawl(conn, [kg()], day=2).notices
    crawl(conn, [row(external_product_id="2", external_variant_id="22")], day=2)
    assert not crawl(conn, [row(external_product_id="2", external_variant_id="22")], day=3).notices


def test_a_container_loses_what_it_holds_with_its_unit(conn):
    crawl(conn, [box()], day=1)
    crawl(conn, [row()], day=2)

    assert tuple(conn.execute(
        "SELECT content_quantity, content_unit_id FROM source_offer").fetchone()) == (None, None)


def test_a_price_that_moved_as_the_unit_went_is_still_a_price_change(conn):
    crawl(conn, [kg(price="10.00")], day=1)
    crawl(conn, [row(price="12.00")], day=2)

    assert len(offers(conn)) == 1
    assert table(conn)[0][1] == 12.00
    assert conn.execute("SELECT COUNT(*) FROM price_observation").fetchone()[0] == 2
    assert conn.execute("SELECT COUNT(*) FROM change_event WHERE change_type = "
                        "'price_increase'").fetchone()[0] == 1, (
        "a real price move beside the lost unit reached no one")


def test_a_unit_that_comes_back_is_learned_by_the_same_offer(conn):
    crawl(conn, [kg()], day=1)
    offer_id = offers(conn)[0][0]
    crawl(conn, [row()], day=2)

    crawl(conn, [kg()], day=3)

    assert [o[:2] for o in offers(conn)] == [(offer_id, "kg")]


def test_a_retired_offer_is_not_a_second_candidate_for_the_lost_unit(conn):
    """MADAR's nails hold a retired `kg` beside a live `box`. There is one offer this row
    can continue, the live one, and counting the retired one would start its history over."""
    crawl(conn, [kg()], day=1)
    crawl(conn, [box()], day=2)
    live_box = next(o[0] for o in offers(conn) if o[4] == "active")

    crawl(conn, [row()], day=3)

    assert len(offers(conn)) == 2, "a retired offer made the lost unit look ambiguous"
    assert [o[0] for o in offers(conn) if o[4] == "active"] == [live_box]


def test_two_stated_units_are_not_guessed_between(conn):
    """A unit-less row could continue either, so it mints. Neither was restated, so both
    retire, and his table shows the one row the shop now states."""
    crawl(conn, [kg(), box()], day=1)

    result = crawl(conn, [row()], day=2)

    assert active(conn) == [(None, 1.0, "SA")]
    assert len(offers(conn)) == 3
    assert any("retired 2 offer" in notice for notice in result.notices), (
        "the job's log gave the wrong count")


# ---- what must not retire ---------------------------------------------------

def test_another_country_of_the_same_variant_stays(conn):
    """GPP_ENERGY: one offer per country on 6 variants, and a run reading some of them
    proves nothing about the rest. Retiring these would empty his fuel table."""
    crawl(conn, [row(country_code_alpha2="AE", currency="AED"),
                 row(country_code_alpha2="AD", currency="EUR")], day=1)

    result = crawl(conn, [row(country_code_alpha2="AE", currency="AED")], day=2)

    assert sorted(active(conn)) == [(None, 1.0, "AD"), (None, 1.0, "AE")]
    assert not any("retired" in notice for notice in result.notices)


def test_a_variant_the_run_did_not_mention_stays(conn):
    """A partial catalogue says nothing about what it did not fetch. The second variant's
    two offers both stand until a run restates that variant."""
    crawl(conn, [kg()], day=1)
    other = dict(external_product_id="2", external_variant_id="22")
    crawl(conn, [row(**other, country_code_alpha2="EG", currency="EGP"),
                 row(**other, country_code_alpha2="*", currency="UNKNOWN")], day=1)

    crawl(conn, [kg()], day=2)

    assert sum(1 for o in offers(conn) if o[4] == "active") == 3


def test_the_same_country_on_a_variant_the_run_did_not_mention_stays(conn):
    """The variant is part of the scope, not only the country: three of his variants hold
    such a pair today, all in SA."""
    other = dict(external_product_id="2", external_variant_id="22")
    crawl(conn, [kg(), box(), kg(**other), box(**other)], day=1)

    crawl(conn, [kg()], day=2)

    assert sum(1 for o in offers(conn) if o[4] == "active") == 3


def test_two_units_the_same_run_states_both_stay(conn):
    """15 per litre and 15 per gallon are two offers, as long as the shop says both."""
    crawl(conn, [kg(), box()], day=1)

    crawl(conn, [kg(), box()], day=2)

    assert sorted(a[0] for a in active(conn)) == ["box", "kg"]


def test_a_run_that_did_not_succeed_retires_nothing(conn):
    """Not seeing something proves nothing when the run did not finish."""
    crawl(conn, [row(country_code_alpha2="*", currency="UNKNOWN")], day=1)
    bad = row(external_product_id="2", external_variant_id="22", price="Call us")

    result = crawl(conn, [row(country_code_alpha2="EG", currency="EGP"), bad], day=2)

    assert result.status.value == "partial"
    assert "*" in {country for _unit, _basis, country in active(conn)}, (
        "a run that did not finish retired an offer")


def test_another_segment_of_the_same_variant_stays(conn):
    """Identity also holds the segment and the branch, and ingest only ever writes
    retail with no branch, so a row it cannot have restated is not its to retire."""
    crawl(conn, [row()], day=1)
    conn.execute(
        "INSERT INTO source_offer (source_variant_id, country_code_alpha2, customer_segment, "
        " currency, tax_included) SELECT source_variant_id, 'SA', 'wholesale', 'SAR', 1 "
        "FROM source_variant")
    conn.execute(
        "INSERT INTO source_offer (source_variant_id, branch_id, country_code_alpha2, "
        " currency, tax_included) SELECT source_variant_id, 'B1', 'SA', 'SAR', 1 "
        "FROM source_variant")

    crawl(conn, [row()], day=2)

    assert len(active(conn)) == 3


def test_another_source_is_never_touched(conn):
    crawl(conn, [row()], day=1)
    other_site = conn.execute(
        "INSERT INTO source_site (source_key, source_name, base_url, platform, currency, "
        " timezone, authority, lifecycle) "
        "VALUES ('OTHER','O','http://o','shopify-json','EGP','UTC','shop','active')").lastrowid
    product = conn.execute(
        "INSERT INTO source_product (source_id, external_product_id) VALUES (?, 'x')",
        (other_site,)).lastrowid
    variant = conn.execute(
        "INSERT INTO source_variant (source_product_id, external_variant_id) VALUES (?, 'y')",
        (product,)).lastrowid
    for country in ("EG", "*"):
        conn.execute(
            "INSERT INTO source_offer (source_variant_id, country_code_alpha2, currency, "
            " tax_included) VALUES (?, ?, 'EGP', 1)", (variant, country))

    crawl(conn, [row()], day=2)

    assert sum(1 for o in offers(conn) if o[4] == "active") == 3


# ---- a row about the past ---------------------------------------------------

def fuel(conn, **over):
    """One commodity row, the only kind that carries a date: GPP_ENERGY's anchors."""
    fields = dict(material_key="DIESEL", country_code_alpha2="EG", currency="EGP",
                  unit="liter", tax_included="1", price_basis="original", price="20.50",
                  provenance="observed")
    fields.update(over)
    builder = RowBuilder(COMMODITY_PRICE)
    table_ = ScrapedTable("GPP_ENERGY", ExtractKind.COMMODITY_PRICE, "https://gpp.example",
                          builder.header, [builder.row(**fields)])
    return ingest_payloads(conn, SourceEntry.model_validate(dict(
        source_key="GPP_ENERGY", source_name="GPP", base_url="https://gpp.example",
        family="static-html-table", cadence="weekly", authority="aggregator", currency="USD",
        extract=[ExtractSpec(kind=ExtractKind.COMMODITY_PRICE, scope=ExtractScope.LATEST_ONLY,
                             materials=["DIESEL"], regions=["*"])])), [table_.to_payload()])


_ANCHOR = dict(provenance="reported", as_of_date="2025-07-20")


def test_an_observed_commodity_row_speaks_for_today(conn):
    """Every real commodity row says `observed` (gpp.py:432, aramco.py:139), and that is a
    statement about today: it brings an offer back and it can take a unit away."""
    fuel(conn)
    fuel(conn, unit="kg")
    assert active(conn) == [("kg", 1.0, "EG")]

    fuel(conn)
    assert active(conn) == [("liter", 1.0, "EG")], "an observed row did not bring it back"

    fuel(conn, unit="")
    assert active(conn) == [(None, 1.0, "EG")], "an observed row did not blank the unit"


def test_a_dated_row_does_not_take_a_unit_away(conn):
    """A reported row is the source's statement about an earlier date, which says nothing
    about what the source states today."""
    fuel(conn)

    fuel(conn, unit="", **_ANCHOR)

    assert active(conn)[0][0] == "liter", "a backfill from 2025 blanked today's unit"


def test_a_dated_row_does_not_revive_a_retired_offer(conn):
    fuel(conn)
    fuel(conn, unit="kg")
    assert active(conn) == [("kg", 1.0, "EG")]

    fuel(conn, **_ANCHOR)

    assert active(conn) == [("kg", 1.0, "EG")], "a backfill brought a retired offer back"


def test_a_dated_row_does_not_revive_a_retired_blank_offer(conn):
    """The other door. A dated row naming a unit reaches the retired unit-less offer through
    the learning path, and it still says nothing about today."""
    fuel(conn)
    fuel(conn, unit="kg")
    fuel(conn)
    fuel(conn, unit="")
    fuel(conn, unit="kg")
    assert active(conn) == [("kg", 1.0, "EG")]

    fuel(conn, unit="liter", **_ANCHOR)

    assert active(conn) == [("kg", 1.0, "EG")], "a backfill brought a retired offer back"


def test_a_dated_row_retires_nothing(conn):
    """It never marks an offer as seen, so it cannot count as a restatement."""
    fuel(conn, country_code_alpha2="*")

    fuel(conn, country_code_alpha2="EG", **_ANCHOR)

    assert "*" in {country for _unit, _basis, country in active(conn)}
