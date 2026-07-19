"""T2: magento-graphql connector against a recorded madar-shaped GraphQL response."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from scrapex import db as dbmod
from scrapex.config import ExtractSpec, SourceEntry
from scrapex.connectors.magento import MagentoGraphqlConnector
from scrapex.ingest import ingest_payloads
from scrapex.rowspec import PRODUCT_PRICES, RowView
from scrapex.vocab import ExtractKind, ExtractScope

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "magento_products.json").read_text(encoding="utf-8"))


class _StubResponse:
    def __init__(self, payload): self._payload = payload
    def json(self): return self._payload


class _StubFetcher:
    """Serves the fixture on page 1, an empty page after (ends pagination)."""
    def __init__(self): self.requests_count = 0
    def post(self, url, json=None, **kwargs):
        self.requests_count += 1
        page = (json or {}).get("variables", {}).get("currentPage", 1)
        return _StubResponse(FIXTURE if page == 1 else {"data": {"products": {"items": []}}})
    def close(self): pass


def make_entry() -> SourceEntry:
    return SourceEntry.model_validate(dict(
        source_key="MADAR", source_name="المدار", base_url="https://www.madar.com",
        family="magento-graphql", currency="SAR", default_region="SA", vat_mode="excl",
        extract=[ExtractSpec(kind=ExtractKind.PRODUCT_PRICES, scope=ExtractScope.CENSUS)],
    ))


def test_magento_maps_variants_and_simple():
    table = next(iter(MagentoGraphqlConnector(_StubFetcher()).fetch(make_entry())))
    assert table.header == list(PRODUCT_PRICES.columns)
    assert len(table.rows) == 3  # 2 variants + 1 simple product

    view = RowView(PRODUCT_PRICES, table.header)
    v12 = view.as_dict(table.rows[0])
    assert v12["external_product_id"] == "NDY3Mg=="       # parent uid
    assert v12["external_variant_id"] == "NDY3MA=="        # child uid — the owner's key rule
    assert v12["external_sku"] == "120151248"
    assert v12["effective_price"] == "112.5"
    assert v12["option_fingerprint"] == "thickness_mm=12"
    assert v12["currency"] == "SAR" and v12["region"] == "SA" and v12["vat_included"] == "0"

    v18 = view.as_dict(table.rows[1])
    assert v18["effective_price"] == "168.78" and v18["regular_price"] == "200.0"  # on sale
    assert v18["sale_price"] == "168.78"

    simple = view.as_dict(table.rows[2])
    assert simple["external_product_id"] == simple["external_variant_id"] == "Q0VNQg=="
    assert simple["availability"] == "out_of_stock"


def test_magento_end_to_end_into_warehouse():
    entry = make_entry()
    table = next(iter(MagentoGraphqlConnector(_StubFetcher()).fetch(entry)))
    conn: sqlite3.Connection = dbmod.connect(":memory:")
    try:
        dbmod.migrate(conn)
        result = ingest_payloads(conn, entry, [table.to_payload()])
    finally:
        conn.close()
    assert result.observations == 3 and result.products == 2 and result.variants == 3
    assert not result.errors
