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

def test_adapter_maps_commodity_row_onto_the_16_product_columns():
    c = RowView(COMMODITY_PRICE, list(COMMODITY_PRICE.columns)).as_dict(commodity_row())
    r = _commodity_to_product_row(c)
    assert set(r) == set(PRODUCT_PRICES.columns)          # exactly the product shape
    assert r["external_product_id"] == "DIESEL" and r["product_name"] == "DIESEL"
    assert r["option_label"] == "USD/liter"               # unit kept verbatim
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
    assert sv[0] is None and sv[1] is None and sv[2] == "USD/liter"
    so = conn.execute("SELECT region, currency, vat_included, selling_unit_id FROM source_offer").fetchone()
    assert so[0] == "EG" and so[1] == "USD" and so[2] == 1 and so[3] is None
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
