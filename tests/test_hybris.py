"""T2: hybris-occ connector — 0-indexed OCC pagination + api-host config + mapping."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from scrapex import db as dbmod
from scrapex.config import ExtractSpec, SourceEntry
from scrapex.connectors.hybris import HybrisOccConnector, _endpoint
from scrapex.ingest import ingest_payloads
from scrapex.rowspec import PRODUCT_PRICES, RowView
from scrapex.vocab import ExtractKind, ExtractScope

FX = Path(__file__).parent / "fixtures"


def _read(name): return (FX / name).read_text(encoding="utf-8")


class _Resp:
    def __init__(self, payload): self._payload = payload
    def json(self): return self._payload


class _StubFetcher:
    """Serves page {currentPage} from the two-page OCC fixture set."""

    def __init__(self): self.requests_count = 0

    def get(self, url, params=None, **kwargs):
        self.requests_count += 1
        page = (params or {}).get("currentPage", 0)
        name = f"hybris_products_page{int(page)}.json"
        return _Resp(json.loads(_read(name)))

    def close(self): pass


def make_entry() -> SourceEntry:
    return SourceEntry.model_validate(dict(
        source_key="MASDAR", source_name="مصدر", base_url="https://www.masdaronline.com",
        family="hybris-occ", currency="SAR", default_region="SA", vat_mode="excl",
        api={"base_url": "https://api.masdaronline.com", "base_site": "masdar"},
        extract=[ExtractSpec(kind=ExtractKind.PRODUCT_PRICES, scope=ExtractScope.CENSUS)],
    ))


def test_endpoint_uses_api_host_not_base_url():
    assert _endpoint(make_entry()) == \
        "https://api.masdaronline.com/rest/v2/masdar/products/search"


def test_endpoint_requires_api_config():
    entry = make_entry().model_copy(update={"api": None})
    with pytest.raises(ValueError, match="needs api.base_url"):
        _endpoint(entry)


def test_hybris_paginates_and_maps():
    fetcher = _StubFetcher()
    table = next(iter(HybrisOccConnector(fetcher).fetch(make_entry())))
    assert fetcher.requests_count == 2          # 0-indexed: pages 0 and 1 (totalPages=2)
    assert len(table.rows) == 3                 # unpriced 1000300 was skipped
    view = RowView(PRODUCT_PRICES, table.header)

    cement = view.as_dict(table.rows[0])
    assert cement["external_product_id"] == "1000123" and cement["external_sku"] == "1000123"
    assert cement["effective_price"] == "25.5" and cement["currency"] == "SAR"
    assert cement["vat_included"] == "0"        # excl -> "0"
    assert cement["availability"] == "in_stock" and cement["stock_quantity"] == "120"
    assert cement["product_url"] == "https://www.masdaronline.com/asmnt/p/1000123"

    rebar = view.as_dict(table.rows[1])
    assert rebar["availability"] == "in_stock"  # lowStock is still purchasable
    assert rebar["product_url"] == "https://www.masdaronline.com/hadid/p/1000200"  # absolute kept
    assert rebar["effective_price"] == "3100"

    sand = view.as_dict(table.rows[2])          # only row on page 1
    assert sand["external_product_id"] == "1000400" and sand["effective_price"] == "15"


def test_hybris_end_to_end_into_warehouse():
    entry = make_entry()
    table = next(iter(HybrisOccConnector(_StubFetcher()).fetch(entry)))
    conn: sqlite3.Connection = dbmod.connect(":memory:")
    try:
        dbmod.migrate(conn)
        result = ingest_payloads(conn, entry, [table.to_payload()])
    finally:
        conn.close()
    assert result.observations == 3 and not result.errors
