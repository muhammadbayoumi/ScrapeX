"""Commodity ingest: a degenerate product (material=product, NULL/NULL variant,
region-per-offer) reusing the product chain via the row-shape adapter. Covers the
column mapping, weekly idempotency by construction, scope guard, and multi-region."""
from __future__ import annotations

import sqlite3

import pytest

from scrapex import db as dbmod
from scrapex.config import ExtractSpec, SourceEntry
from scrapex.ingest import _commodity_to_product_row, ingest_payloads
from scrapex.payload import PAYLOAD_VERSION, FunnelPayload
from scrapex.rowspec import COMMODITY_PRICE, PRODUCT_PRICES, RowBuilder, RowView
from scrapex.vocab import ExtractKind, ExtractScope

GPP_MATERIALS = ["DIESEL", "GASOLINE", "LPG", "ELECTRICITY", "NATURAL_GAS"]


@pytest.fixture()
def conn() -> sqlite3.Connection:
    c = dbmod.connect(":memory:")
    dbmod.migrate(c)
    yield c
    c.close()


def commodity_entry(**over) -> SourceEntry:
    base = dict(
        source_key="GPP_ENERGY", source_name="أسعار الطاقة العالمية",
        base_url="https://www.globalpetrolprices.com", family="static-html-table",
        authority="aggregator", cadence="weekly",
        extract=[ExtractSpec(kind=ExtractKind.COMMODITY_PRICE, scope=ExtractScope.LATEST_ONLY,
                             materials=GPP_MATERIALS, regions=["*"])],
    )
    base.update(over)
    return SourceEntry.model_validate(base)


def commodity_row(**over) -> list[str]:
    fields = dict(
        material_key="DIESEL", region="EG", currency="USD", unit="USD/liter",
        vat_included="1", effective_price="0.620", observed_label="Mar 2026",
    )
    fields.update(over)
    return RowBuilder(COMMODITY_PRICE).row(**fields)


def commodity_payload(rows, source_key="GPP_ENERGY", scraped_at="2026-07-16T10:00:00Z") -> FunnelPayload:
    return FunnelPayload(
        payload_version=PAYLOAD_VERSION, source_key=source_key,
        kind=ExtractKind.COMMODITY_PRICE, client="cli", scraped_at=scraped_at,
        source_url="https://www.globalpetrolprices.com/diesel_prices/",
        header=list(COMMODITY_PRICE.columns), rows=rows,
    )


# ---- the adapter (pure) ------------------------------------------------------

def test_adapter_maps_commodity_row_onto_every_product_column():
    c = RowView(COMMODITY_PRICE, list(COMMODITY_PRICE.columns)).as_dict(commodity_row())
    r = _commodity_to_product_row(c)
    assert set(r) == set(PRODUCT_PRICES.columns)          # exactly the product shape
    assert r["external_product_id"] == "DIESEL" and r["product_name"] == "DIESEL"
    # The unit goes to its own column and nowhere else. It used to be stuffed
    # into option_label, where a unit was indistinguishable from a variant
    # title like "Red / Large".
    assert r["unit"] == "USD/liter"
    assert r["option_label"] == ""
    assert r["region"] == "EG" and r["currency"] == "USD" and r["effective_price"] == "0.620"
    assert r["external_variant_id"] == "" and r["option_fingerprint"] == ""  # NULL/NULL variant
    assert r["regular_price"] == "" and r["sale_price"] == ""
    assert "observed_label" not in r                      # dropped, never read


# ---- full chain --------------------------------------------------------------

def test_commodity_creates_degenerate_chain(conn):
    result = ingest_payloads(conn, commodity_entry(), [commodity_payload([commodity_row()])])
    assert (result.products, result.variants, result.observations) == (1, 1, 1)

    sp = conn.execute("SELECT external_product_id, has_variants FROM source_product").fetchone()
    assert sp[0] == "DIESEL" and sp[1] == 0
    sv = conn.execute("SELECT external_variant_id, option_fingerprint, option_label "
                      "FROM source_variant").fetchone()
    # option_label is empty now: a commodity has no variant title, and the unit
    # it used to borrow this column for has a real home.
    assert sv[0] is None and sv[1] is None and sv[2] is None
    so = conn.execute(
        "SELECT so.region, so.currency, so.vat_included, su.unit_code, so.basis_quantity "
        "FROM source_offer so LEFT JOIN selling_unit su USING (selling_unit_id)").fetchone()
    assert so[0] == "EG" and so[1] == "USD" and so[2] == 1
    # 'USD/liter' is a currency the offer already records plus a unit. Storing
    # it whole would make 'USD/liter' and 'EGP/liter' two different litres.
    assert so[3] == "liter", "the unit was not resolved, or kept its currency"
    assert so[4] == 1
    po = conn.execute("SELECT business_date, effective_price, regular_price, sale_price "
                      "FROM price_observation").fetchone()
    assert po[0] == "2026-07-16" and po[1] == 0.620 and po[2] is None and po[3] is None


# ---- weekly idempotency BY CONSTRUCTION --------------------------------------

def test_same_day_recrawl_is_idempotent(conn):
    entry = commodity_entry()
    ingest_payloads(conn, entry, [commodity_payload([commodity_row()])])
    second = ingest_payloads(conn, entry, [commodity_payload([commodity_row()])])
    assert second.observations == 0 and second.confirmed == 1
    assert conn.execute("SELECT COUNT(*) FROM price_observation").fetchone()[0] == 1


def test_same_day_price_change_appends(conn):
    entry = commodity_entry()
    ingest_payloads(conn, entry, [commodity_payload([commodity_row()])])
    changed = ingest_payloads(conn, entry, [commodity_payload([commodity_row(effective_price="0.700")])])
    assert changed.observations == 1  # same offer+business_date, new record_hash -> append
    dates = [r[0] for r in conn.execute("SELECT business_date FROM price_observation")]
    assert dates == ["2026-07-16", "2026-07-16"]  # append-only keeps both, same day


def test_next_week_at_the_same_price_confirms_rather_than_appends(conn):
    """This test asserted the opposite, and its old name said so out loud.

    Until the owner defined the price-history semantics, every weekly crawl
    appended a row whether or not the price had moved — a year of unchanged
    diesel was 52 identical "history" entries. The history is now a timeline of
    real changes, so the second crawl CONFIRMS the price it already knows.
    """
    entry = commodity_entry()
    ingest_payloads(conn, entry, [commodity_payload([commodity_row()])])
    nextwk = ingest_payloads(conn, entry, [commodity_payload(
        [commodity_row()], scraped_at="2026-07-23T10:00:00Z")])

    assert nextwk.observations == 0 and nextwk.confirmed == 1
    assert conn.execute("SELECT COUNT(*) FROM price_observation").fetchone()[0] == 1
    # ...and the confirmation is recorded, so the price is known to still hold.
    assert conn.execute(
        "SELECT last_confirmed_at FROM offer_state").fetchone()[0] == "2026-07-23T10:00:00Z"


def test_a_real_weekly_change_still_appends(conn):
    entry = commodity_entry()
    ingest_payloads(conn, entry, [commodity_payload([commodity_row()])])
    moved = ingest_payloads(conn, entry, [commodity_payload(
        [commodity_row(effective_price="0.990")], scraped_at="2026-07-23T10:00:00Z")])
    assert moved.observations == 1
    assert conn.execute("SELECT COUNT(*) FROM price_period").fetchone()[0] == 2


# ---- scope guard on material -------------------------------------------------

def test_out_of_scope_material_is_rejected(conn):
    result = ingest_payloads(conn, commodity_entry(),
                             [commodity_payload([commodity_row(material_key="GASOLINE_91")])])
    assert result.rejected_out_of_scope == 1
    assert conn.execute("SELECT COUNT(*) FROM price_observation").fetchone()[0] == 0


# ---- region-per-offer + one variant per material -----------------------------

def test_two_regions_share_one_variant_two_offers(conn):
    rows = [commodity_row(region="EG"), commodity_row(region="SA")]
    result = ingest_payloads(conn, commodity_entry(), [commodity_payload(rows)])
    assert (result.products, result.variants, result.observations) == (1, 1, 2)
    assert conn.execute("SELECT COUNT(*) FROM source_offer").fetchone()[0] == 2
    assert {r[0] for r in conn.execute("SELECT region FROM source_offer")} == {"EG", "SA"}


def test_multi_material_one_variant_each_no_dup_on_recrawl(conn):
    entry = commodity_entry()
    rows = [commodity_row(material_key="DIESEL"), commodity_row(material_key="LPG", unit="USD/liter")]
    first = ingest_payloads(conn, entry, [commodity_payload(rows)])
    assert (first.products, first.variants, first.observations) == (2, 2, 2)
    second = ingest_payloads(conn, entry, [commodity_payload(rows)])
    assert second.variants == 0 and second.observations == 0  # idempotent, no new variants
    assert conn.execute("SELECT COUNT(*) FROM source_variant").fetchone()[0] == 2


# ---- the unit is part of what an offer IS ------------------------------------

def test_the_same_fuel_in_different_units_is_two_offers(conn):
    """15 per litre and 15 per gallon are different prices, not one price that
    stayed the same. The offer lookup used to pin selling_unit_id IS NULL, so
    every offer was unit-less and these two collapsed into one."""
    ingest_payloads(conn, commodity_entry(), [commodity_payload([commodity_row()])])
    gallon = commodity_row()
    gallon[COMMODITY_PRICE.index("unit")] = "USD/US Gallon"
    ingest_payloads(conn, commodity_entry(), [commodity_payload([gallon])])

    offers = conn.execute(
        "SELECT su.unit_code FROM source_offer so "
        "LEFT JOIN selling_unit su USING (selling_unit_id) ORDER BY 1").fetchall()

    assert [o[0] for o in offers] == ["liter", "us gallon"], \
        "one fuel priced in two units collapsed into a single offer"


def test_the_same_unit_spelled_differently_is_one_offer(conn):
    """'liter' and 'litres' are the same litre. Two rows would split one price
    series in two and make every crawl look like the price moved."""
    ingest_payloads(conn, commodity_entry(), [commodity_payload([commodity_row()])])
    respelled = commodity_row()
    respelled[COMMODITY_PRICE.index("unit")] = "USD/Litres"
    ingest_payloads(conn, commodity_entry(), [commodity_payload([respelled])])

    assert conn.execute("SELECT count(*) FROM source_offer").fetchone()[0] == 1
    assert conn.execute("SELECT count(*) FROM selling_unit").fetchone()[0] == 1


def test_a_currency_change_does_not_mint_a_second_unit(conn):
    """'USD/liter' and 'EGP/liter' are one physical litre. Storing the currency
    inside the unit would make them two."""
    from scrapex.ingest import canonical_unit

    assert canonical_unit("USD/liter", "USD") == "liter"
    assert canonical_unit("EGP/liter", "EGP") == "liter"
    # A genuine compound unit must survive: this is not a currency prefix.
    assert canonical_unit("kg/m2", "USD") == "kg/m2"


def test_an_unrecognised_unit_is_kept_rather_than_guessed_at():
    """A wrong merge silently makes two different things one price series.
    An extra row in a lookup table costs nothing."""
    from scrapex.ingest import canonical_unit

    assert canonical_unit("bundle of 12", "SAR") == "bundle of 12"
    assert canonical_unit("", "SAR") == ""


def test_a_roll_and_an_offcut_are_not_the_same_price(conn):
    """Sameh Gabriel sells cable by length: 500 for a 100 m roll and 500 for a
    1 m piece are not the same price, and comparing them as if they were is
    exactly what the basis quantity exists to prevent."""
    from scrapex.ingest import _unit_with_basis

    assert _unit_with_basis({"unit": "m", "basis_quantity": "100"}) == "100 m"
    assert _unit_with_basis({"unit": "m", "basis_quantity": "1"}) == "m"
    assert _unit_with_basis({"unit": "m", "basis_quantity": ""}) == "m"
    assert _unit_with_basis({"unit": "", "basis_quantity": "100"}) == ""


def test_a_unit_change_opens_a_new_price_period_not_a_price_change(conn):
    """The pricekey docstring promised that 15 USD/litre and 15 USD/gallon are
    different series. That held for fuel and quietly did not hold for products,
    because the slot carried a variant title instead of the unit."""
    ingest_payloads(conn, commodity_entry(), [commodity_payload([commodity_row()])])
    gallon = commodity_row()
    gallon[COMMODITY_PRICE.index("unit")] = "USD/US Gallon"
    ingest_payloads(conn, commodity_entry(), [commodity_payload([gallon])])

    keys = {row[0] for row in conn.execute("SELECT price_hash FROM price_observation")}
    assert len(keys) == 2, "the same number under two units hashed to one price"
    fields = {row[0] for row in conn.execute("SELECT price_fields FROM price_observation")}
    assert all("unit" in f for f in fields), "the unit never reached the price key"
