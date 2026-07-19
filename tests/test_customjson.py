"""T2: custom-json-api connector — /api/products mapping + specail_price semantics."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from scrapex import db as dbmod
from scrapex.config import ExtractSpec, SourceEntry
from scrapex.connectors.custom_json import CustomJsonConnector, _prices
from scrapex.ingest import ingest_payloads
from scrapex.rowspec import PRODUCT_PRICES, RowView
from scrapex.vocab import ExtractKind, ExtractScope

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "sikaegshop_products.json").read_text(encoding="utf-8"))


class _Resp:
    def __init__(self, payload): self._payload = payload
    def json(self): return self._payload


class _StubFetcher:
    def __init__(self): self.requests_count = 0
    def get(self, url, **kwargs):
        self.requests_count += 1
        return _Resp(FIXTURE)
    def close(self): pass


def make_entry() -> SourceEntry:
    return SourceEntry.model_validate(dict(
        source_key="SIKAEGSHOP", source_name="سيكا مصر شوب", base_url="https://www.sikaegshop.com",
        family="custom-json-api", currency="EGP", default_region="EG", vat_mode="incl",
        extract=[ExtractSpec(kind=ExtractKind.PRODUCT_PRICES, scope=ExtractScope.CENSUS)],
    ))


# ---- pure price semantics ----------------------------------------------------

def test_prices_specail_is_the_discount():
    assert _prices({"price": 350, "specail_price": 300}) == ("350", "300", "300")


def test_prices_zero_specail_means_no_sale():
    assert _prices({"price": 120, "specail_price": 0}) == ("120", "", "120")


def test_prices_unpriced_is_empty():
    assert _prices({"price": 0, "specail_price": 0}) == ("", "", "")


# ---- full fetch --------------------------------------------------------------

def test_customjson_maps_and_skips_unpriced():
    fetcher = _StubFetcher()
    table = next(iter(CustomJsonConnector(fetcher).fetch(make_entry())))
    assert fetcher.requests_count == 1        # full catalog in one call
    assert len(table.rows) == 2               # 503 (no price) skipped
    view = RowView(PRODUCT_PRICES, table.header)

    adhesive = view.as_dict(table.rows[0])
    assert adhesive["external_product_id"] == "501" and adhesive["external_sku"] == "SIKA-ADH-20"
    assert adhesive["product_name"] == "مادة لاصقة سيكا 20 كجم"   # Arabic name preferred
    assert adhesive["regular_price"] == "350" and adhesive["sale_price"] == "300"
    assert adhesive["effective_price"] == "300" and adhesive["currency"] == "EGP"
    assert adhesive["vat_included"] == "1" and adhesive["availability"] == "in_stock"
    assert adhesive["product_url"] == "https://www.sikaegshop.com/product/sika-adhesive-20"

    sealant = view.as_dict(table.rows[1])
    assert sealant["effective_price"] == "120" and sealant["sale_price"] == ""
    assert sealant["availability"] == "out_of_stock"


def test_customjson_end_to_end_into_warehouse():
    entry = make_entry()
    table = next(iter(CustomJsonConnector(_StubFetcher()).fetch(entry)))
    conn: sqlite3.Connection = dbmod.connect(":memory:")
    try:
        dbmod.migrate(conn)
        result = ingest_payloads(conn, entry, [table.to_payload()])
    finally:
        conn.close()
    assert result.observations == 2 and not result.errors
