"""Reports: the two-layer summary + bounded sample."""
from __future__ import annotations

import sqlite3

import pytest

from scrapex import db as dbmod
from scrapex.reports import recent_observations, source_summary
from tests.test_ingest import make_entry, make_payload, one_row
from scrapex.ingest import ingest_payloads


@pytest.fixture()
def conn() -> sqlite3.Connection:
    c = dbmod.connect(":memory:")
    dbmod.migrate(c)
    yield c
    c.close()


def test_summary_none_for_unknown_source(conn):
    assert source_summary(conn, "NOPE") is None


def test_summary_reports_source_local_layer(conn):
    ingest_payloads(conn, make_entry(), [make_payload([
        one_row(external_product_id="1", external_variant_id="v1"),
        one_row(external_product_id="2", external_variant_id="v2", effective_price="50.00"),
    ])])
    s = source_summary(conn, "ELSEWEDYSHOP")
    assert s.products == 2 and s.variants == 2 and s.observations == 2
    assert s.curation == {"inventoried": 2}
    # Unified layer is empty until curation — this is the point of the report.
    assert s.matched_variants == 0 and s.published_rows == 0
    assert s.last_status == "success"


def test_recent_observations_is_bounded_and_shaped(conn):
    rows = [one_row(external_product_id=str(i), external_variant_id=f"v{i}",
                    effective_price=f"{i+1}.00") for i in range(5)]
    ingest_payloads(conn, make_entry(), [make_payload(rows)])
    sample = recent_observations(conn, "ELSEWEDYSHOP", limit=3)
    assert len(sample) == 3
    assert set(sample[0]) == {"name", "price", "currency", "availability", "vat_included",
                              "business_date", "region", "region_name", "unit"}
    assert sample[0]["currency"] == "EGP"


def test_summary_curation_breakdown_reflects_ignore(conn):
    ingest_payloads(conn, make_entry(), [make_payload([one_row()])])
    conn.execute("UPDATE source_product SET curation_status = 'ignored'")
    s = source_summary(conn, "ELSEWEDYSHOP")
    assert s.curation == {"ignored": 1}


# ---- region / country surfacing (the owner-reported defect) -----------------

def _commodity_rows(conn, regions=("EG", "SA"), price="0.404"):
    """Ingest one commodity row per country, the GPP shape."""
    from scrapex.config import ExtractSpec, SourceEntry
    from scrapex.payload import PAYLOAD_VERSION, FunnelPayload
    from scrapex.rowspec import COMMODITY_PRICE, RowBuilder
    from scrapex.vocab import ExtractKind, ExtractScope

    entry = SourceEntry.model_validate(dict(
        source_key="GPP_ENERGY", source_name="Global energy prices",
        base_url="https://www.globalpetrolprices.com", family="static-html-table",
        currency="USD", authority="aggregator", cadence="weekly",
        extract=[ExtractSpec(kind=ExtractKind.COMMODITY_PRICE, scope=ExtractScope.LATEST_ONLY,
                             materials=["DIESEL"], regions=["*"])]))
    rows = [RowBuilder(COMMODITY_PRICE).row(
        material_key="DIESEL", region=r, currency="USD", unit="USD/liter",
        vat_included="1", effective_price=price, observed_label="") for r in regions]
    ingest_payloads(conn, entry, [FunnelPayload(
        payload_version=PAYLOAD_VERSION, source_key="GPP_ENERGY",
        kind=ExtractKind.COMMODITY_PRICE, client="cli", scraped_at="2026-07-19T10:00:00Z",
        source_url="https://www.globalpetrolprices.com",
        header=list(COMMODITY_PRICE.columns), rows=rows)])
    return entry


def test_iso_code_resolves_to_a_country_name():
    from scrapex.reports import region_name
    assert region_name("EG") == "Egypt" and region_name("SA") == "Saudi Arabia"
    assert region_name("ZZ") == "ZZ"          # unknown code passes through
    assert region_name("*") == "" and region_name(None) == ""   # no geography = blank


def test_browse_exposes_the_country_for_commodity_rows(conn):
    """Regression: prices arrived but the country was invisible — ~180 rows
    rendered byte-identical except for the price."""
    from scrapex.reports import browse_observations
    _commodity_rows(conn)
    rows = browse_observations(conn, "GPP_ENERGY").rows
    assert {r["region"] for r in rows} == {"EG", "SA"}
    assert {r["region_name"] for r in rows} == {"Egypt", "Saudi Arabia"}
    assert rows[0] != rows[1]                 # the rows are now distinguishable


def test_browse_can_search_by_country(conn):
    """Search matched product name only, so "EG" found nothing on a commodity source."""
    from scrapex.reports import browse_observations
    _commodity_rows(conn)
    assert browse_observations(conn, "GPP_ENERGY", search="EG").total == 1
    assert browse_observations(conn, "GPP_ENERGY", search="DIESEL").total == 2


def test_browse_order_is_stable_for_identical_rows(conn):
    from scrapex.reports import browse_observations
    _commodity_rows(conn, regions=("EG", "SA", "US", "AE"))
    first = [r["region"] for r in browse_observations(conn, "GPP_ENERGY").rows]
    second = [r["region"] for r in browse_observations(conn, "GPP_ENERGY").rows]
    assert first == second == sorted(first)


def test_export_carries_region_and_country(conn):
    from scrapex.reports import EXPORT_HEADER, export_source_table
    _commodity_rows(conn)
    header, table = export_source_table(conn, "GPP_ENERGY")
    assert header == EXPORT_HEADER
    assert header[1] == "region" and header[2] == "country"
    assert {row[1] for row in table} == {"EG", "SA"}
    assert {row[2] for row in table} == {"Egypt", "Saudi Arabia"}


def test_product_sources_show_no_country_rather_than_a_star(conn):
    """A shop has no per-row geography; '*' must read as blank, not an asterisk."""
    from scrapex.reports import export_source_table
    ingest_payloads(conn, make_entry(default_region="*"), [make_payload([one_row(region="*")])])
    _, table = export_source_table(conn, "ELSEWEDYSHOP")
    assert table[0][1] == "" and table[0][2] == ""


def test_search_accepts_the_country_NAME_not_only_the_code(conn):
    """The region is stored as a code but a person searches by name — typing
    "Egypt" must find the Egyptian row, not zero rows."""
    from scrapex.reports import browse_observations, region_code
    _commodity_rows(conn, regions=("EG", "SA", "US"))
    assert region_code("Egypt") == "EG" and region_code("Saudi Arabia") == "SA"
    assert region_code("EG") == "" and region_code("nonsense") == ""

    assert browse_observations(conn, "GPP_ENERGY", search="Egypt").total == 1
    assert browse_observations(conn, "GPP_ENERGY", search="EG").total == 1
    assert browse_observations(conn, "GPP_ENERGY", search="Saudi Arabia").total == 1
