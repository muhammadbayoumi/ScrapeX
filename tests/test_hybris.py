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
    """Serves page {currentPage} from the two-page OCC fixture set.

    LANGUAGES is what the store's own /languages endpoint reports. The
    connector asks before deciding whether an English pass is worth any
    requests at all, so a single-language store stays a one-pass crawl.
    """

    LANGUAGES = [{"isocode": "ar", "active": True}]

    def __init__(self): self.requests_count = 0

    def get(self, url, params=None, **kwargs):
        self.requests_count += 1
        if url.endswith("/languages"):
            return _Resp({"languages": self.LANGUAGES})
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


def price_rows(connector, entry):
    """Rows, warnings and checkpoints across every yielded table.

    hybris yields ONE TABLE PER PAGE since the resume work (#70): it used to
    accumulate the whole catalogue and yield once, so an interrupted crawl had
    written nothing to the journal. These tests care about the rows.
    """
    header, rows, warnings, tokens = None, [], [], []
    for table in connector.fetch(entry):
        header = header or table.header
        rows.extend(table.rows)
        warnings.extend(table.warnings)
        if table.page_token:
            tokens.append(table.page_token)
    return header, rows, warnings, tokens


def test_hybris_paginates_and_maps():
    fetcher = _StubFetcher()
    header, rows, warnings, tokens = price_rows(HybrisOccConnector(fetcher), make_entry())
    # /languages once, then 0-indexed pages 0 and 1 (totalPages=2). The store
    # here publishes one language, so no second pass is fetched.
    assert fetcher.requests_count == 3
    assert len(rows) == 3                 # unpriced 1000300 was skipped
    view = RowView(PRODUCT_PRICES, header)

    cement = view.as_dict(rows[0])
    assert cement["external_product_id"] == "1000123" and cement["external_sku"] == "1000123"
    assert cement["price"] == "25.5" and cement["currency"] == "SAR"
    assert cement["tax_included"] == "0"        # excl -> "0"
    assert cement["availability"] == "in_stock" and cement["stock_quantity"] == "120"
    # No salesUnit in this fixture -> the plain join stands, never a guessed prefix.
    assert cement["product_link"] == "https://www.masdaronline.com/asmnt/p/1000123"

    rebar = view.as_dict(rows[1])
    assert rebar["availability"] == "in_stock"  # lowStock is still purchasable
    assert rebar["product_link"] == "https://www.masdaronline.com/hadid/p/1000200"  # absolute kept
    assert rebar["price"] == "3100"

    sand = view.as_dict(rows[2])          # only row on page 1
    assert sand["external_product_id"] == "1000400" and sand["price"] == "15"


def test_the_unpriced_products_are_skipped_OUT_LOUD():
    """714 of masdar's 1353 products answer price: null (live, 2026-07-23).

    Skipping them is right — they are absent from the storefront's own sitemap,
    so they are genuinely off sale. Skipping them in silence made a crawl that
    landed 639 of 1353 report plain success.
    """
    header, rows, warnings, tokens = price_rows(HybrisOccConnector(_StubFetcher()), make_entry())

    assert any("no price at all" in w for w in warnings)
    assert any("1 product(s)" in w for w in warnings)


# ---- live captures: api.masdaronline.com, 2026-07-23 -------------------------

LIVE = FX / "live"


def _live(name): return json.loads((LIVE / name).read_text(encoding="utf-8"))


class _LiveStubFetcher:
    """Serves the 2026-07-23 masdar captures, ar or en per the `lang` param."""

    def __init__(self): self.requests_count = 0

    def get(self, url, params=None, **kwargs):
        self.requests_count += 1
        if url.endswith("/languages"):
            return _Resp({"languages": [{"isocode": "en", "active": True},
                                        {"isocode": "ar", "active": True}]})
        lang = (params or {}).get("lang", "ar")
        if int((params or {}).get("currentPage", 0)) > 0:
            return _Resp({"products": [], "pagination": {"totalPages": 1}})
        return _Resp(_live(f"masdar_hybris_occ_search_{lang}_2026-07-23.json"))

    def close(self): pass


def _live_rows():
    header, rows, warnings, tokens = price_rows(HybrisOccConnector(_LiveStubFetcher()), make_entry())
    return rows, RowView(PRODUCT_PRICES, header)


def test_the_product_url_is_the_page_the_storefront_actually_serves():
    """The API states only the tail; joining it onto the host 404s on EVERY
    masdar product. The storefront files each product under
    /{lang}/{currency}/{sales-unit}/ — verified against masdaronline's own
    Product sitemap, which matched the composed URL for all 639 priced
    products with zero mismatches, and the page answers 200.
    """
    rows, view = _live_rows()
    switch = view.as_dict(rows[0])

    assert switch["external_product_id"] == "1000035833"
    assert switch["product_link"] == (
        "https://www.masdaronline.com/ar/sar/pce/electrical-supplies-and-equipment"
        "/switches-and-sockets/sockets/alfanar-new-alf-switch-1gang-20a-double-pole"
        "-7-7cm-with-neon-ab104/p/1000035833")
    # The unit segment is READ from each product's salesUnit, never fixed:
    # PCE above, EA and DR here — three units across three products.
    assert "/ar/sar/ea/" in view.as_dict(rows[1])["product_link"]
    assert "/ar/sar/dr/" in view.as_dict(rows[2])["product_link"]


def test_the_english_name_the_same_api_publishes_is_captured_beside_the_arabic():
    """The standing bilingual rule. OCC takes `lang` per request and masdar's
    own /languages endpoint lists ar and en as active, so the English name
    costs one extra pass over the same endpoint — and 1331 of 1346 live
    products answered with a genuinely different name."""
    rows, view = _live_rows()
    switch = view.as_dict(rows[0])

    assert switch["product_name_ar"] == (
        "الفنار ألف جديد مفتاح سخان مفرد 20 أمبير 7*7 سم أبيضAB104-وطني")
    assert switch["product_name"] == (
        "ALFANAR NEW ALF SWITCH 20A 1GANG  DOUBLE POLE 7*7cm WITH NEON AB104")
    assert switch["lang"] == "ar"   # the language we asked for, not a guess


def test_a_single_language_store_is_never_crawled_twice():
    """The English pass is gated on the STORE saying it publishes English."""
    class _ArabicOnly(_LiveStubFetcher):
        def get(self, url, params=None, **kwargs):
            if url.endswith("/languages"):
                self.requests_count += 1
                return _Resp({"languages": [{"isocode": "ar", "active": True}]})
            return super().get(url, params=params, **kwargs)

    fetcher = _ArabicOnly()
    header, rows, warnings, tokens = price_rows(HybrisOccConnector(fetcher), make_entry())

    assert fetcher.requests_count == 3   # languages + page 0 + the empty page 1
    assert all(RowView(PRODUCT_PRICES, header).get(r, "product_name") == ""
               for r in rows)


def test_a_failed_english_pass_costs_a_note_never_the_prices():
    class _EnglishBroken(_LiveStubFetcher):
        def get(self, url, params=None, **kwargs):
            if (params or {}).get("lang") == "en":
                raise RuntimeError("502 from the OCC host")
            return super().get(url, params=params, **kwargs)

    header, rows, warnings, tokens = price_rows(HybrisOccConnector(_EnglishBroken()), make_entry())

    assert len(rows) == 3
    assert any("english-names pass failed" in w for w in warnings)


def test_hybris_end_to_end_into_warehouse():
    entry = make_entry()
    tables = list(HybrisOccConnector(_StubFetcher()).fetch(entry))
    conn: sqlite3.Connection = dbmod.connect(":memory:")
    try:
        dbmod.migrate(conn)
        result = ingest_payloads(conn, entry, [t.to_payload() for t in tables])
    finally:
        conn.close()
    assert result.observations == 3 and not result.errors
