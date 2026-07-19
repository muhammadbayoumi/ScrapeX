"""T2: woocommerce-storeapi connector — minor-unit price conversion + mapping."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from scrapex import db as dbmod
from scrapex.config import ExtractSpec, SourceEntry
from scrapex.connectors.woocommerce import WooCommerceConnector
from scrapex.ingest import ingest_payloads
from scrapex.rowspec import PRODUCT_PRICES, RowView
from scrapex.vocab import ExtractKind, ExtractScope

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "woocommerce_products.json").read_text(encoding="utf-8"))


class _StubResponse:
    def __init__(self, payload): self._payload = payload
    def json(self): return self._payload


class _StubFetcher:
    def __init__(self): self.requests_count = 0
    def get(self, url, params=None, **kwargs):
        self.requests_count += 1
        page = (params or {}).get("page", 1)
        return _StubResponse(FIXTURE if page == 1 else [])
    def close(self): pass


def make_entry() -> SourceEntry:
    return SourceEntry.model_validate(dict(
        source_key="SAMEHGABRIEL", source_name="سامح جبرائيل", base_url="https://samehgabriel.com",
        family="woocommerce-storeapi", currency="EGP", default_region="EG", vat_mode="incl",
        extract=[ExtractSpec(kind=ExtractKind.PRODUCT_PRICES, scope=ExtractScope.CENSUS)],
    ))


def test_woo_converts_minor_units_and_maps():
    table = next(iter(WooCommerceConnector(_StubFetcher()).fetch(make_entry())))
    assert len(table.rows) == 2
    view = RowView(PRODUCT_PRICES, table.header)

    wire = view.as_dict(table.rows[0])
    assert wire["external_product_id"] == "10150"
    assert wire["effective_price"] == "450.00"   # "45000" minor_unit 2 -> 450.00
    assert wire["regular_price"] == "500.00"      # on sale
    assert wire["sale_price"] == "450.00"
    assert wire["currency"] == "EGP" and wire["vat_included"] == "1"
    assert wire["availability"] == "in_stock"

    breaker = view.as_dict(table.rows[1])
    assert breaker["effective_price"] == "125.50" and breaker["sale_price"] == ""
    assert breaker["availability"] == "out_of_stock"


def test_woo_end_to_end_into_warehouse():
    entry = make_entry()
    table = next(iter(WooCommerceConnector(_StubFetcher()).fetch(entry)))
    conn: sqlite3.Connection = dbmod.connect(":memory:")
    try:
        dbmod.migrate(conn)
        result = ingest_payloads(conn, entry, [table.to_payload()])
    finally:
        conn.close()
    assert result.observations == 2 and not result.errors
