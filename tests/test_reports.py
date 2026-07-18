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
    assert set(sample[0]) == {"name", "price", "currency", "availability", "vat_included", "business_date"}
    assert sample[0]["currency"] == "EGP"


def test_summary_curation_breakdown_reflects_ignore(conn):
    ingest_payloads(conn, make_entry(), [make_payload([one_row()])])
    conn.execute("UPDATE source_product SET curation_status = 'ignored'")
    s = source_summary(conn, "ELSEWEDYSHOP")
    assert s.curation == {"ignored": 1}
