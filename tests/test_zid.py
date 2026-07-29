"""T2: zid-html connector — sitemap /products/ filter, JSON-LD parse, Chrome UA wiring."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from scrapex import db as dbmod
from scrapex.config import ExtractSpec, SourceEntry
from scrapex.connectors.base import (CrawlBlocked, DEFAULT_USER_AGENT,
                                    HttpFetcher, resolve_fetcher)
from scrapex.connectors.jsonld import alternate_links, english_alternate
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


# ---- bilingual: advancedcastle serves ar AND en, 2026-07-28 ----------------

# The five alternates advancedcastle's own <head> publishes on every page.
LIVE_ALTERNATES = {
    "ar-eg": "https://advancedcastle.com/ar-eg/products/CO2-extinguisher",
    "en": "https://advancedcastle.com/en/products/CO2-extinguisher",
    "en-eg": "https://advancedcastle.com/en-eg/products/CO2-extinguisher",
    "ar-sa": "https://advancedcastle.com/products/CO2-extinguisher",
    "x-default": "https://advancedcastle.com/products/CO2-extinguisher",
}

_ONE_PRODUCT_SITEMAP = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>'
    "https://advancedcastle.com/products/CO2-extinguisher"
    "</loc></url></urlset>"
)


class _BilingualStubFetcher:
    """The captured ar-sa page and the en page it advertises."""

    AR = "live/advancedcastle_product_ar_2026-07-28.trimmed.html"
    EN = "live/advancedcastle_product_en_2026-07-28.trimmed.html"

    def __init__(self):
        self.requests_count = 0
        self.urls = []

    def get(self, url, **kwargs):
        self.requests_count += 1
        self.urls.append(url)
        if url.endswith("/sitemap.xml"):
            return _Resp(_ONE_PRODUCT_SITEMAP)
        if "/en/products/" in url:
            return _Resp(_read(self.EN))
        if "/products/" in url:
            return _Resp(_read(self.AR))
        raise RuntimeError("404 " + url)

    def close(self): pass


def test_the_english_page_the_store_publishes_fills_the_unmarked_columns():
    """advancedcastle serves BOTH languages and says so in its own <head>, yet
    the connector emitted Arabic-only rows. The standing bilingual rule makes
    that a defect, not a gap."""
    fetcher = _BilingualStubFetcher()
    header, rows, warnings, _t = price_rows(ZidConnector(fetcher), make_entry())
    view = RowView(PRODUCT_PRICES, header)
    row = view.as_dict(rows[0])

    # Both halves, each from the page that published it — nothing translated.
    assert row["product_name_ar"] == "طفاية حريق ثاني أكسيد الكربون CO2 سعة 6 كجم"
    assert row["product_name"] == "6kg CO₂ Fire Extinguisher"
    assert row["category_path_ar"] == "أنظمة الإطفاء > طفايات الحريق اليدوية"
    assert row["category_path"] == "Extinguish Systems > Manual fire extinguishers"
    # One product, one identity: the English page is the SAME sku, so it must
    # not have become a second product.
    assert len(rows) == 1 and row["external_sku"] == "e1mf0901"
    assert not warnings
    # The English page is a real second request, and the SA-region one.
    assert "https://advancedcastle.com/en/products/CO2-extinguisher" in fetcher.urls


def test_the_english_page_is_read_for_text_and_never_for_price():
    """Both SA pages quote SAR 285. The row's money must come from the page the
    crawl is anchored on, so a later change to which alternate is fetched can
    never move a price."""
    header, rows, _w, _t = price_rows(ZidConnector(_BilingualStubFetcher()),
                                      make_entry())
    row = RowView(PRODUCT_PRICES, header).as_dict(rows[0])
    assert row["price"] == "285.00" and row["currency"] == "SAR"
    assert row["country_code_alpha2"] == "SA"


def test_an_arabic_only_store_advertises_nothing_and_pays_nothing():
    """The 2026-07-20 capture carries no alternates. Such a store must cost
    exactly one request per product, and its unmarked column must stay EMPTY
    rather than be filled with the Arabic text under an English heading."""
    class _Recording(_LiveStubFetcher):
        def __init__(self):
            super().__init__()
            self.urls = []

        def get(self, url, **kwargs):
            self.urls.append(url)
            return super().get(url, **kwargs)

    fetcher = _Recording()
    header, rows, warnings, _t = price_rows(ZidConnector(fetcher), make_entry())
    view = RowView(PRODUCT_PRICES, header)

    assert rows
    assert all(view.as_dict(r)["product_name"] == "" for r in rows)
    assert all(view.as_dict(r)["category_path"] == "" for r in rows)
    # Not one request was spent looking for a language this store never
    # advertised, and every product page was fetched exactly once.
    assert not any("/en/" in u or "/en-eg/" in u for u in fetcher.urls)
    assert len(fetcher.urls) == len(set(fetcher.urls))
    assert not any("English" in w for w in warnings)


def test_an_alternate_pointing_at_a_different_product_is_refused():
    """A mis-wired hreflang must not write another product's English name onto
    this row. Empty and warned beats plausible and wrong."""
    class _WrongProduct(_BilingualStubFetcher):
        def get(self, url, **kwargs):
            if "/en/products/" in url:
                self.requests_count += 1
                return _Resp(_read(_LiveStubFetcher.PRODUCT_PAGE))  # other sku
            return super().get(url, **kwargs)

    header, rows, warnings, _t = price_rows(ZidConnector(_WrongProduct()),
                                            make_entry())
    row = RowView(PRODUCT_PRICES, header).as_dict(rows[0])
    assert row["product_name"] == ""
    assert row["product_name_ar"]          # the Arabic capture is untouched
    assert any("English page" in w for w in warnings)


def test_an_unreachable_english_page_warns_rather_than_passing_silently():
    class _DeadEnglish(_BilingualStubFetcher):
        def get(self, url, **kwargs):
            if "/en/products/" in url:
                raise RuntimeError("503")
            return super().get(url, **kwargs)

    header, rows, warnings, _t = price_rows(ZidConnector(_DeadEnglish()),
                                            make_entry())
    assert RowView(PRODUCT_PRICES, header).as_dict(rows[0])["product_name"] == ""
    assert any("English page" in w and "1 product(s)" in w for w in warnings)


def test_a_blocked_english_page_stops_the_crawl():
    class _BlockedEnglish(_BilingualStubFetcher):
        def get(self, url, **kwargs):
            if "/en/products/" in url:
                raise CrawlBlocked("owner or site stopped the crawl")
            return super().get(url, **kwargs)

    with pytest.raises(CrawlBlocked):
        list(ZidConnector(_BlockedEnglish()).fetch(make_entry()))


def test_the_english_alternate_taken_is_the_one_for_our_region():
    """When the page advertises both, the region-matched English alternate wins
    deliberately rather than whichever the document listed first."""
    assert (english_alternate(LIVE_ALTERNATES, "SA")
            == "https://advancedcastle.com/en/products/CO2-extinguisher")
    assert (english_alternate(LIVE_ALTERNATES, "EG")
            == "https://advancedcastle.com/en-eg/products/CO2-extinguisher")
    # An Arabic-only store: no English page, and we invent none.
    assert english_alternate({"ar-sa": "https://x/y"}, "SA") == ""


def test_alternate_links_reads_the_stores_own_codes():
    links = alternate_links(_read(_BilingualStubFetcher.AR))
    assert links == LIVE_ALTERNATES


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
