"""T2: zid-html connector — sitemap /products/ filter, JSON-LD parse, Chrome UA wiring."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from scrapex import db as dbmod
from scrapex.config import ExtractSpec, SourceEntry
from scrapex.connectors.base import DEFAULT_USER_AGENT, HttpFetcher, resolve_fetcher
from scrapex.connectors.zid import ZidConnector
from scrapex.ingest import ingest_payloads
from scrapex.rowspec import PRODUCT_PRICES, RowView
from scrapex.vocab import ExtractKind, ExtractScope

FX = Path(__file__).parent / "fixtures"
CHROME_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/125.0.0.0 Safari/537.36"


def _read(name): return (FX / name).read_text(encoding="utf-8")


class _Resp:
    def __init__(self, text): self.text = text


class _StubFetcher:
    ROUTES = {
        "/sitemap.xml": "zid_sitemap.xml",
        "/sitemap-products.xml": "zid_subsitemap.xml",
        "/products/cement-bag": "zid_product_simple.html",
        "/products/rebar-12": "zid_product_variant.html",
    }

    def __init__(self): self.requests_count = 0

    def get(self, url, **kwargs):
        self.requests_count += 1
        for needle, fixture in self.ROUTES.items():
            if url.endswith(needle):
                return _Resp(_read(fixture))
        raise RuntimeError("404 " + url)

    def close(self): pass


def make_entry() -> SourceEntry:
    return SourceEntry.model_validate(dict(
        source_key="ADVANCEDCASTLE", source_name="القلعة المتقدمة", base_url="https://advancedcastle.com",
        family="zid-html", currency="SAR", default_region="SA", vat_mode="incl", user_agent=CHROME_UA,
        extract=[ExtractSpec(kind=ExtractKind.PRODUCT_PRICES, scope=ExtractScope.CENSUS)],
    ))


def test_resolve_fetcher_uses_source_user_agent():
    fetcher = resolve_fetcher(make_entry())
    try:
        assert isinstance(fetcher, HttpFetcher)
        assert fetcher._client.headers["user-agent"] == CHROME_UA
    finally:
        fetcher.close()


def test_resolve_fetcher_defaults_ua_when_unset():
    entry = make_entry().model_copy(update={"user_agent": None})
    fetcher = resolve_fetcher(entry)
    try:
        assert fetcher._client.headers["user-agent"] == DEFAULT_USER_AGENT
    finally:
        fetcher.close()


def test_zid_filters_products_and_maps():
    table = next(iter(ZidConnector(_StubFetcher()).fetch(make_entry())))
    assert len(table.rows) == 2  # /about-us filtered out (no /products/)
    view = RowView(PRODUCT_PRICES, table.header)

    cement = view.as_dict(table.rows[0])
    assert cement["external_product_id"] == "AC-CEMENT-01"  # from JSON-LD sku
    assert cement["external_sku"] == "AC-CEMENT-01"
    assert cement["effective_price"] == "45" and cement["currency"] == "SAR"
    assert cement["vat_included"] == "1" and cement["availability"] == "in_stock"
    assert cement["product_url"] == "https://advancedcastle.com/products/cement-bag"

    rebar = view.as_dict(table.rows[1])
    assert rebar["external_product_id"] == "rebar-12"  # no sku -> URL slug fallback
    assert rebar["external_sku"] == ""
    assert rebar["effective_price"] == "300"  # AggregateOffer lowPrice fallback


def test_zid_end_to_end_into_warehouse():
    entry = make_entry()
    table = next(iter(ZidConnector(_StubFetcher()).fetch(entry)))
    conn: sqlite3.Connection = dbmod.connect(":memory:")
    try:
        dbmod.migrate(conn)
        result = ingest_payloads(conn, entry, [table.to_payload()])
    finally:
        conn.close()
    assert result.observations == 2 and not result.errors
