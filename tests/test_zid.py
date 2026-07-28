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


def price_rows(connector, entry):
    """Rows, warnings and checkpoints across every yielded table.

    zid yields ONE TABLE PER PRODUCT since the resume work (#70): accumulating
    the catalogue and yielding once at the end meant an interrupted crawl had
    written nothing to the journal. These tests care about the rows, not the
    granularity, so they read them the way capture does.
    """
    header, rows, warnings, tokens = None, [], [], []
    for table in connector.fetch(entry):
        header = header or table.header
        rows.extend(table.rows)
        warnings.extend(table.warnings)
        if table.page_token:
            tokens.append(table.page_token)
    return header, rows, warnings, tokens


def test_zid_filters_products_and_maps():
    header, rows, _w, tokens = price_rows(ZidConnector(_StubFetcher()), make_entry())
    assert len(rows) == 2  # /about-us filtered out (no /products/)
    assert len(set(tokens)) == 2, "one checkpoint per product, and distinct"
    view = RowView(PRODUCT_PRICES, header)

    cement = view.as_dict(rows[0])
    assert cement["external_product_id"] == "AC-CEMENT-01"  # from JSON-LD sku
    assert cement["external_sku"] == "AC-CEMENT-01"
    assert cement["price"] == "45" and cement["currency"] == "SAR"
    assert cement["tax_included"] == "1" and cement["availability"] == "in_stock"
    assert cement["product_link"] == "https://advancedcastle.com/products/cement-bag"
    # Arabic-only source: the marked column carries the name and the
    # unmarked one stays EMPTY, so the heading never asserts a language
    # the cell does not hold.
    assert cement["product_name_ar"] and cement["product_name"] == ""

    rebar = view.as_dict(rows[1])
    assert rebar["external_product_id"] == "rebar-12"  # no sku -> URL slug fallback
    assert rebar["external_sku"] == ""
    assert rebar["price"] == "300"  # AggregateOffer lowPrice fallback


# ---- live capture: advancedcastle.com, 2026-07-20 / 2026-07-23 --------------

class _LiveStubFetcher:
    """Serves the captured advancedcastle sitemaps and one captured product page."""

    ROUTES = {
        "/sitemap.xml": "live/advancedcastle_sitemap_index.xml",
        "/sitemap_products.xml": "live/advancedcastle_sitemap_products.trimmed.xml",
    }
    PRODUCT_PAGE = "live/advancedcastle_product.trimmed.html"

    def __init__(self): self.requests_count = 0

    def get(self, url, **kwargs):
        self.requests_count += 1
        for needle, fixture in self.ROUTES.items():
            if url.endswith(needle):
                return _Resp(_read(fixture))
        if "/products/" in url:
            return _Resp(_read(self.PRODUCT_PAGE))
        raise RuntimeError("404 " + url)

    def close(self): pass


def test_the_category_the_live_page_states_rides_the_row():
    """advancedcastle's product JSON-LD carries `category` — «كاشف دخان» in
    this 2026-07-20 capture, «قفل عجلات > مخفض» on the 2026-07-23 page. The
    connector parsed the very same node for the price and dropped the filing,
    leaving category_path empty on every Zid row."""
    header, rows, _w, _t = price_rows(ZidConnector(_LiveStubFetcher()), make_entry())
    view = RowView(PRODUCT_PRICES, header)

    assert rows, "the live capture must produce rows"
    assert view.as_dict(rows[0])["category_path_ar"] == "كاشف دخان"
    assert view.as_dict(rows[0])["availability"] == "in_stock"


def test_a_zid_page_that_cannot_be_read_leaves_a_warning():
    """Zid skipped unreadable and unpriced pages in total silence, so a crawl
    that landed half the catalogue reported plain success — the lesson salla
    and GPP already paid for."""
    class _OneBadPage(_LiveStubFetcher):
        def get(self, url, **kwargs):
            if url.endswith("/3-pack-battery-powered-smoke-detectors"):
                self.requests_count += 1
                return _Resp("<html><body>no json-ld here</body></html>")
            return super().get(url, **kwargs)

    _h, _rows, warnings, _t = price_rows(ZidConnector(_OneBadPage()), make_entry())

    assert any("no Product" in w and "1 product page(s)" in w
               for w in warnings)


def test_zid_end_to_end_into_warehouse():
    entry = make_entry()
    tables = list(ZidConnector(_StubFetcher()).fetch(entry))
    conn: sqlite3.Connection = dbmod.connect(":memory:")
    try:
        dbmod.migrate(conn)
        result = ingest_payloads(conn, entry, [t.to_payload() for t in tables])
    finally:
        conn.close()
    assert result.observations == 2 and not result.errors
