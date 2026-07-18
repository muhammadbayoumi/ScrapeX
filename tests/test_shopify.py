"""T2: shopify-json connector against a recorded real-shape products.json.

Exact-value assertions; a stub fetcher replays the fixture (and a second empty
page to end pagination), so the parse is pinned with zero network.
"""
from __future__ import annotations

import json
from pathlib import Path

from scrapex.config import ExtractSpec, SourceEntry
from scrapex.connectors.shopify import ShopifyConnector
from scrapex.rowspec import PRODUCT_PRICES, RowView
from scrapex.vocab import ExtractKind, ExtractScope

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "shopify_products.json").read_text(encoding="utf-8"))


class _StubResponse:
    def __init__(self, payload): self._payload = payload
    def json(self): return self._payload


class _StubFetcher:
    """Serves the fixture on page 1, an empty page on page 2 (pagination end)."""
    def __init__(self): self.requests_count = 0; self.urls: list[str] = []
    def get(self, url, **kwargs):
        self.requests_count += 1
        self.urls.append(url)
        page_one = "page=1" in url
        return _StubResponse(FIXTURE if page_one else {"products": []})
    def close(self): pass


def make_entry() -> SourceEntry:
    return SourceEntry.model_validate(dict(
        source_key="ELSEWEDYSHOP", source_name="السويدي شوب",
        base_url="https://elsewedyshop.com", family="shopify-json",
        currency="EGP", default_region="EG", vat_mode="incl",
        extract=[ExtractSpec(kind=ExtractKind.PRODUCT_PRICES, scope=ExtractScope.CENSUS)],
    ))


def test_shopify_maps_variants_to_rows():
    fetcher = _StubFetcher()
    tables = list(ShopifyConnector(fetcher).fetch(make_entry()))
    assert len(tables) == 1
    table = tables[0]
    assert table.header == list(PRODUCT_PRICES.columns)
    assert len(table.rows) == 3  # 2 variants + 1 variant

    view = RowView(PRODUCT_PRICES, table.header)
    first = view.as_dict(table.rows[0])
    assert first["external_product_id"] == "10157311557932"
    assert first["external_variant_id"] == "52388706844972"
    assert first["external_sku"] == "105003"
    assert first["effective_price"] == "1200.00"
    assert first["regular_price"] == "1450.00"   # compare_at_price
    assert first["sale_price"] == "1200.00"       # on sale -> sale price present
    assert first["option_fingerprint"] == "color temp=6500k"
    assert first["vat_included"] == "1"
    assert first["region"] == "EG"
    assert first["currency"] == "EGP"
    assert first["availability"] == "in_stock"
    assert first["product_url"] == "https://elsewedyshop.com/products/led-floodlight-400w-ip65"


def test_shopify_out_of_stock_and_no_sale():
    table = next(iter(ShopifyConnector(_StubFetcher()).fetch(make_entry())))
    view = RowView(PRODUCT_PRICES, table.header)
    second = view.as_dict(table.rows[1])  # 3000K variant
    assert second["availability"] == "out_of_stock"
    assert second["sale_price"] == ""             # no compare_at -> not on sale
    assert second["regular_price"] == "1180.00"


def test_shopify_default_title_variant_has_no_fingerprint():
    table = next(iter(ShopifyConnector(_StubFetcher()).fetch(make_entry())))
    view = RowView(PRODUCT_PRICES, table.header)
    wire = view.as_dict(table.rows[2])  # copper wire, single Default Title variant
    assert wire["option_fingerprint"] == ""
    assert wire["option_label"] == ""
    assert wire["external_sku"] == "312890"


def test_shopify_end_to_end_into_warehouse():
    """The whole loop: connector rows -> payload -> ingest -> price_observation."""
    import sqlite3

    from scrapex import db as dbmod
    from scrapex.ingest import ingest_payloads

    entry = make_entry()
    table = next(iter(ShopifyConnector(_StubFetcher()).fetch(entry)))
    conn: sqlite3.Connection = dbmod.connect(":memory:")
    try:
        dbmod.migrate(conn)
        result = ingest_payloads(conn, entry, [table.to_payload()])
    finally:
        conn.close()
    assert result.observations == 3 and result.products == 2 and result.variants == 3
    assert not result.errors
