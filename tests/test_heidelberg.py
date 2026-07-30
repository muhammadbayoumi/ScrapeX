"""T2: heidelberg-price-matrix — the three filters that turn 211 numbers into
the 108 prices the storefront can actually render, the api-host split, and the
cement family read off a THIRD host because the store publishes no taxonomy.

Every store fixture is a live capture of 2026-07-29; see
tests/fixtures/live/heidelberg_2026-07-29.CAPTURE.md for what was fetched, what
was trimmed and the census the trim preserves. The corporate fixtures are
2026-07-30 — heidelberg_corporate_2026-07-30.CAPTURE.md.
"""
from __future__ import annotations

import copy
import json
import sqlite3
from pathlib import Path

import pytest

from scrapex import db as dbmod
from scrapex.config import ExtractSpec, SourceEntry
from scrapex.connectors.heidelberg import (
    _FAMILY_BY_DESIGNATION, HeidelbergPriceMatrixConnector, _api_root, _price)
from scrapex.ingest import ingest_payloads
from scrapex.rowspec import ENRICHMENT, PRODUCT_PRICES, RowView
from scrapex.vocab import DetailGroup, ExtractKind, ExtractScope, group_for_code

LIVE = Path(__file__).parent / "fixtures" / "live"
_FILES = {
    "Products": "heidelberg_products_2026-07-29.json",
    "Plants": "heidelberg_plants_2026-07-29.json",
    "ProductsPrices": "heidelberg_products_prices_2026-07-29.json",
}
# The corporate host, keyed by the PATH the connector asks for — two languages
# of one listing, which is the whole of the taxonomy read.
_PAGES = {
    "/en/our-products": "heidelberg_corporate_products_en_2026-07-30.trimmed.html",
    "/ar/our_products_ar": "heidelberg_corporate_products_ar_2026-07-30.trimmed.html",
}
FAMILIES_EVIDENCE = "heidelberg_corporate_families_2026-07-30.json"

CORPORATE = "https://www.heidelbergmaterials.eg"
TAXONOMY = {"base_url": CORPORATE, "listing_path": "/en/our-products",
            "listing_path_ar": "/ar/our_products_ar"}

# Anchors read out of the capture, so a test says WHICH product it means.
SUEZ_MULTI = "1000007e-32a9-4324-8ed9-117b0c47389f"     # isMultiPlant, own plant Y210
HELWAN_SINGLE = "4ce38978-903b-4a28-9aec-f3498c38f990"  # isMultiPlant false, own plant Y410
# Cairo prices both of them at the same six figures, which is what makes the
# pair a clean test of the plant rule and of nothing else.
CAIRO = "e46739d4-31a5-420a-b540-a6d859fb6cd6"
DAHAB = "eab70d2e-b602-442f-bfd1-08dac8c1d154"
# The one product no city prices: catalogued, active, and quoted nowhere.
TOURAH_UNPRICED = "6217a245-4758-4ca3-b19a-ae83eb4ad347"
# The packaging type that used to fill category_path, in both languages. Named
# here so every guard against it reads as one fact rather than two literals.
PACKAGING, PACKAGING_AR = "Bagged", "معبأ"


def _fixture(name: str):
    return json.loads((LIVE / _FILES[name]).read_text(encoding="utf-8"))


def _page(path: str) -> str:
    return (LIVE / _PAGES[path]).read_text(encoding="utf-8")


class _Resp:
    def __init__(self, payload=None, text=""):
        self._payload, self.text = payload, text

    def json(self):
        if self._payload is None:
            raise ValueError("not JSON")
        return self._payload


class _StubFetcher:
    """Serves the captured tables by endpoint name and the captured corporate
    listing by path. `pages` overrides or removes a listing; a page mapped to
    None raises, which is how the host-is-down path is exercised."""

    def __init__(self, tables: dict | None = None, pages: dict | None = None):
        self.requests_count = 0
        self.asked: list[str] = []
        self._tables = tables or {}
        self._pages = pages or {}

    def get(self, url, **kwargs):
        self.requests_count += 1
        self.asked.append(url)
        if url.startswith(CORPORATE):
            path = url[len(CORPORATE):]
            if path in self._pages:
                markup = self._pages[path]
                if markup is None:
                    raise RuntimeError(f"stub: {path} is down")
                return _Resp(text=markup)
            return _Resp(text=_page(path))
        name = url.rsplit("/", 1)[-1]
        if name in self._tables:
            return _Resp(self._tables[name])
        return _Resp(_fixture(name))

    def close(self): pass


def make_entry(**overrides) -> SourceEntry:
    fields = dict(
        source_key="HEIDELBERG_EG",
        source_name="Heidelberg Materials Egypt Online Store",
        base_url="https://onlinestore.heidelbergmaterials.eg",
        family="heidelberg-price-matrix", currency="EGP", default_region="EG",
        vat_mode="incl",
        api={"base_url": "https://onlinestoreapi.heidelbergmaterials.eg"},
        taxonomy=dict(TAXONOMY),
        extract=[ExtractSpec(kind=ExtractKind.PRODUCT_PRICES, scope=ExtractScope.CENSUS),
                 ExtractSpec(kind=ExtractKind.ENRICHMENT, scope=ExtractScope.CENSUS)],
    )
    fields.update(overrides)
    return SourceEntry.model_validate(fields)


def crawl(fetcher=None, entry=None):
    """(price rows as dicts, warnings, enrichment rows as dicts, fetcher)."""
    fetcher = fetcher or _StubFetcher()
    entry = entry or make_entry()
    prices, warnings, enrichment = [], [], []
    for table in HeidelbergPriceMatrixConnector(fetcher).fetch(entry):
        warnings.extend(table.warnings)
        if table.kind == PRODUCT_PRICES.kind:
            view = RowView(PRODUCT_PRICES, table.header)
            prices.extend(view.as_dict(row) for row in table.rows)
        else:
            view = RowView(ENRICHMENT, table.header)
            enrichment.extend(view.as_dict(row) for row in table.rows)
    return prices, warnings, enrichment, fetcher


def defects_of(fetcher=None, entry=None) -> list[str]:
    """Only the DEFECTS — a degraded run, distinct from a contained warning."""
    found: list[str] = []
    for table in HeidelbergPriceMatrixConnector(
            fetcher or _StubFetcher()).fetch(entry or make_entry()):
        found.extend(table.defects)
    return found


# ---- the split host ---------------------------------------------------------

def test_the_data_host_is_the_api_one_never_the_storefront():
    """The storefront serves static files and 404s every API path. This is the
    single reason custom-json-api cannot serve this source: it composes
    f"{source.base_url}/api/products" and never reads source.api."""
    assert _api_root(make_entry()) == "https://onlinestoreapi.heidelbergmaterials.eg/api"


def test_without_the_api_host_it_refuses_rather_than_guesses():
    with pytest.raises(ValueError, match="needs api.base_url"):
        _api_root(make_entry(api=None))


def test_the_whole_source_is_five_requests():
    """Two tables would do it if any product were assigned to Y220. None is —
    all 9 sit on Y210 or Y410 — so /api/Plants is what makes «القطامية»
    the site's word rather than our transliteration.

    The fourth and fifth are the corporate taxonomy, ONE PER LANGUAGE and once
    for the whole source. This is the cost ceiling: 5 for 108 prices, 8
    products' details and 5 cement families. Nothing here is per-product, and
    no family page is fetched at crawl time."""
    _prices, _w, _e, fetcher = crawl()
    assert fetcher.requests_count == 5
    assert fetcher.asked == [
        "https://onlinestoreapi.heidelbergmaterials.eg/api/Products",
        "https://onlinestoreapi.heidelbergmaterials.eg/api/Plants",
        "https://onlinestoreapi.heidelbergmaterials.eg/api/ProductsPrices",
        f"{CORPORATE}/en/our-products",
        f"{CORPORATE}/ar/our_products_ar",
    ]


def test_the_taxonomy_is_read_once_not_once_per_product():
    """8 products share 4 families. A reader that asked per product would be 8
    requests where 2 do, and the whole virtue of this source is that it is cheap.
    """
    _prices, _w, _e, fetcher = crawl()
    assert sum(1 for url in fetcher.asked if url.startswith(CORPORATE)) == 2


# ---- the three filters ------------------------------------------------------

def test_the_matrix_yields_exactly_the_prices_the_storefront_can_render():
    """211 numbers live in the table; 108 of them are prices a visitor can be
    shown. Every one of the 103 refusals is named in a warning, because a crawl
    that files half of what it read and says nothing reads as a complete one."""
    prices, warnings, _e, _f = crawl()

    assert len(prices) == 108
    assert len({(r["external_product_id"], r["external_variant_id"]) for r in prices}) == 108
    assert any("10 price(s) belong to a customer segment other than Y6" in w for w in warnings)
    assert any("5 price(s) sit on rows the API flags isActive=false" in w for w in warnings)
    assert any("88 price(s) are for a plant column" in w for w in warnings)


def test_the_002_sentinel_is_refused_because_it_is_not_two_piastres():
    """The storefront's own test is `salePrice30Y410>.1`, and 0.02 is POSITIVE
    — the ordinary "non-positive means no price" rule lets it straight through
    as a two-piastre tonne of cement."""
    assert _price({"salePriceY210": 0.02}, "salePriceY210") is None
    assert _price({"salePriceY210": 0.0}, "salePriceY210") is None
    assert _price({"salePriceY210": 0.1}, "salePriceY210") is None      # the boundary itself
    assert _price({"salePriceY210": 3950.02}, "salePriceY210") == 3950.02
    assert _price({"salePriceY210": None}, "salePriceY210") is None

    prices, _w, _e, _f = crawl()
    assert all(float(r["price"]) > 0.1 for r in prices)
    assert "0.02" not in {r["price"] for r in prices}


def test_a_row_whose_every_column_is_the_sentinel_produces_nothing():
    table = copy.deepcopy(_fixture("ProductsPrices"))
    for row in table:
        for plant in ("Y210", "Y220", "Y410"):
            row[f"salePrice{plant}"] = 0.02
            row[f"salePrice30{plant}"] = 0.0
    prices, _w, _e, _f = crawl(_StubFetcher({"ProductsPrices": table}))
    assert prices == []


def test_the_plant_rule_follows_isMultiPlant_and_nothing_else():
    """Cairo prices two products identically and populates ALL SIX columns for
    both. One is isMultiPlant, one is not — so the same six numbers become four
    rows for the first and two for the second, which is what their pages show.
    """
    prices, _w, _e, _f = crawl()
    plants_of = lambda pid: sorted(  # noqa: E731
        r["external_variant_id"].split("|")[1] for r in prices
        if r["external_product_id"] == pid and r["external_variant_id"].startswith(CAIRO))

    # isMultiPlant: the two-option dropdown, Y210 and Y220. NEVER Y410 — the
    # multi-plant branch of the template has no Y410 option at all.
    assert plants_of(SUEZ_MULTI) == ["Y210", "Y210", "Y220", "Y220"]
    # not multi-plant: only the product's OWN plants.plantCode, even though the
    # row states a Y210 and a Y220 price beside it.
    assert plants_of(HELWAN_SINGLE) == ["Y410", "Y410"]


def test_only_the_segment_an_anonymous_visitor_is_quoted_is_recorded():
    """The bundle hard-codes segment="Y6". The 10 non-Y6 prices are YM/YT and
    every one is for Dahab, which the API flags inactive — unreachable twice
    over."""
    table = _fixture("ProductsPrices")
    non_public = {r["cityId"] for r in table
                  if r["companyTypes"]["sapCode"] in ("YM", "YT")
                  and any(v > 0.1 for k, v in r.items() if k.startswith("salePrice"))}
    assert non_public, "the capture must still contain the YM/YT prices this test refuses"

    prices, warnings, _e, _f = crawl()
    assert not [r for r in prices if r["external_variant_id"].split("|")[0] in non_public]
    assert any("not quotable to an anonymous visitor" in w for w in warnings)


def test_inactive_price_rows_are_dropped_so_the_two_endpoints_cannot_disagree():
    """/api/ProductsPrices returns inactive rows; the storefront's own
    GetProductsPricesByCityIdAndSegment does not. Flipping isActive on must
    therefore ADD rows, and flipping it off must leave none."""
    off = copy.deepcopy(_fixture("ProductsPrices"))
    for row in off:
        row["isActive"] = False
    assert crawl(_StubFetcher({"ProductsPrices": off}))[0] == []

    on = copy.deepcopy(_fixture("ProductsPrices"))
    for row in on:
        row["isActive"] = True
    rows = crawl(_StubFetcher({"ProductsPrices": on}))[0]
    # Every row the flag was hiding is for Dahab — the city the API also flags
    # inactive — and 3 of its 5 Y6 prices survive the plant rule beside it.
    assert len(rows) == 111
    base = {r["external_variant_id"] for r in crawl()[0]}
    assert {r["external_variant_id"].split("|")[0] for r in rows
            if r["external_variant_id"] not in base} == {DAHAB}


# ---- what a row says --------------------------------------------------------

def test_the_bilingual_pair_is_productName_and_never_productLabel():
    """productLabelEn == productLabelAr on all 9 — the same Latin string stored
    twice. It is a DESIGNATION, not a name, and reading it as the Arabic name
    would fill every Arabic cell with "CEMII / A-P 42,5N SUEZ"."""
    prices, _w, enrichment, _f = crawl()
    suez = next(r for r in prices if r["external_product_id"] == SUEZ_MULTI)

    assert suez["product_name"] == "Suez"            # productNameEn
    assert suez["product_name_ar"] == "السويس"        # productNameAr, entity-decoded
    assert suez["lang"] == "ar"
    designation = next(r for r in enrichment
                       if r["external_product_id"] == SUEZ_MULTI
                       and r["attribute_code"] == "cement_type")
    assert designation["raw_value"] == "CEMII / A-P 42,5N SUEZ"
    assert "CEMII" not in suez["product_name_ar"]


def test_arabic_arrives_entity_encoded_and_is_decoded_before_it_is_filed():
    """The live API returns `&#1571;&#1587;…` while the prerendered HTML returns
    the same text plain. File the raw string and the entities become the name."""
    raw = next(p for p in _fixture("Products") if p["id"] == SUEZ_MULTI)
    assert "&#1571;" in raw["productShortDescriptionAr"]

    _p, _w, enrichment, _f = crawl()
    described = next(r for r in enrichment if r["external_product_id"] == SUEZ_MULTI
                     and r["attribute_code"] == "description_ar")
    assert "&#" not in described["raw_value"]
    assert described["raw_value"].startswith("أسمنت بورتلاند")


def test_the_tier_carries_the_merchants_own_sap_material_number():
    """The merchant issues a DIFFERENT SAP code per bracket — 2122671 under
    30 t, 2112671 at 30 t and above — so the tier is his distinction, not one
    we drew, and the sku says which bracket a row is."""
    prices, _w, _e, _f = crawl()
    cairo_suez = {r["external_variant_id"]: r for r in prices
                  if r["external_product_id"] == SUEZ_MULTI
                  and r["external_variant_id"].startswith(CAIRO)}

    low = cairo_suez[f"{CAIRO}|Y210|2122671"]
    high = cairo_suez[f"{CAIRO}|Y210|2112671"]
    assert (low["external_sku"], low["price"]) == ("2122671", "4000.02")
    assert (high["external_sku"], high["price"]) == ("2112671", "3900.02")
    assert "من 1 الى 29 طن" in low["variant_ar"]
    assert "من 30 طن فأكثر" in high["variant_ar"]


def test_the_english_axes_omit_the_quantity_the_site_publishes_in_arabic_only():
    """Owner ruling 2026-07-29: the bracket is Arabic-only on the site, so the
    English side stays EMPTY rather than be authored here. City and plant ARE
    published in both, so both are filled."""
    prices, _w, _e, _f = crawl()
    row = next(r for r in prices if r["external_variant_id"] == f"{CAIRO}|Y220|2112671")

    assert json.loads(row["variant_axes"]) == {"City": "Cairo", "Plant": "Katameya"}
    assert json.loads(row["variant_axes_ar"]) == {
        "المدينة": "القاهرة", "المصنع": "القطامية", "الكمية": "من 30 طن فأكثر"}


def test_the_price_is_the_matrix_never_maxPrice():
    """maxPrice (1950) and exWorkMaxPrice (1700) ride every product and the
    bundle references them zero times. The matrix prices the same product at
    3950.02 — recording maxPrice would publish half the real number."""
    product = next(p for p in _fixture("Products") if p["id"] == SUEZ_MULTI)
    assert (product["maxPrice"], product["exWorkMaxPrice"]) == (1950.0, 1700.0)

    prices, _w, _e, _f = crawl()
    assert {"1950", "1700"} & {r["price"] for r in prices} == set()


def test_no_discount_is_manufactured_where_the_site_draws_none():
    """isOnSale is false on all 2,070 price rows and every fakePrice column is
    a sentinel, while five of the nine PRODUCTS carry isOnSale=true with
    nothing behind it."""
    flagged = [p["id"] for p in _fixture("Products") if p["isOnSale"]]
    assert len(flagged) == 5

    prices, _w, _e, _f = crawl()
    assert all(r["price_before"] == "" and r["price_sale"] == "" for r in prices)
    assert all(r["price_trade"] == "" for r in prices)


def test_the_row_states_the_unit_the_currency_and_the_tax_basis():
    prices, _w, _e, _f = crawl()
    row = prices[0]
    assert (row["unit"], row["basis_quantity"]) == ("tonne", "1")   # « / للطن »
    assert (row["currency"], row["country_code_alpha2"]) == ("EGP", "EG")
    assert row["tax_included"] == "1"
    assert row["availability"] == "in_stock"    # the API has no stock concept


def test_the_product_link_is_the_client_side_route_and_is_never_fetched():
    """/productinfo/{guid} 404s at IIS — there is no SPA fallback rewrite. It is
    recorded for a human to open, and the crawl must never follow it."""
    prices, _w, _e, fetcher = crawl()
    assert prices[0]["product_link"] == (
        "https://onlinestore.heidelbergmaterials.eg/productinfo/"
        + prices[0]["external_product_id"])
    assert not any("/productinfo/" in url for url in fetcher.asked)


# ---- the category: a cement family, never a packaging type -------------------

# What the corporate site publishes today, per store designation. The values are
# the site's; this table is here so a test can say WHICH family it means.
_EXPECTED = {
    "CEMII / A-P 42,5N SUEZ": ("Suez, Helwan, Tourah", "السويس، حلوان، طره"),
    "CEMII / A-P 42,5N HELWAN": ("Suez, Helwan, Tourah", "السويس، حلوان، طره"),
    "CEM IV/A (P) 42.5N SR": ("Sulphate Resistant", "المقاوم للكبريتات"),
    "CEM IV/A (P) 42.5N SR / Super": ("Sulphate Resistant", "المقاوم للكبريتات"),
    "OASIS MC 22.5X SUEZ": ("Suez Oasis, Helwan Oasis", "الواحة السويس، الواحة حلوان"),
    "OASIS MC 22.5X HELWAN": ("Suez Oasis, Helwan Oasis", "الواحة السويس، الواحة حلوان"),
    "CEMIII / A 42.5N Suez": ("Blast Furnace Cement", "أسمنت خبث الأفران"),
}


def test_the_category_is_never_the_packaging_type():
    """THE REGRESSION THIS FILE EXISTS TO CATCH. `productTypes` is `Bagged` on
    all 9 products — one value across the catalogue, distinguishing nothing —
    and it used to fill category_path. If it ever comes back, here."""
    prices, _w, _e, _f = crawl()

    assert PACKAGING not in {r["category_path"] for r in prices}
    assert PACKAGING_AR not in {r["category_path_ar"] for r in prices}
    # And not by the back door either: the packaging type's GUID was what
    # category_external_id used to hold.
    assert "6b9192c9-706a-47e8-b47d-71db2412865a" not in {
        r["category_external_id"] for r in prices}
    # A category that distinguishes nothing is the defect, so assert it now
    # distinguishes: 4 families over the 8 priced products, not 1 over 9.
    assert len({r["category_path"] for r in prices}) == 4


def test_every_row_carries_the_family_the_corporate_site_publishes():
    """All 108, in both languages, with the site's own words on both sides."""
    prices, _w, _e, _f = crawl()
    products = {p["id"]: p for p in _fixture("Products")}

    seen = set()
    for row in prices:
        designation = products[row["external_product_id"]]["productLabelEn"].strip()
        expected_en, expected_ar = _EXPECTED[designation]
        assert row["category_path"] == expected_en, designation
        assert row["category_path_ar"] == expected_ar, designation
        seen.add(designation)
    assert seen == set(_EXPECTED), "a designation in the capture went uncategorised"
    assert len(prices) == 108


def test_no_translation_the_site_publishes_is_dropped():
    """The corporate site publishes all five families in BOTH languages, so a
    row with an English category and no Arabic one is a defect, not a source
    that answers in one language. Asserted as an invariant over every row
    rather than per family, so a future family cannot slip through half-filled.
    """
    prices, _w, _e, _f = crawl()

    for row in prices:
        assert bool(row["category_path"]) == bool(row["category_path_ar"]), row
        # Never the same string in both columns: that is a Latin designation
        # copied into an Arabic cell, which is what cement_type exists to avoid.
        assert row["category_path"] != row["category_path_ar"]
    assert all(r["category_path"] for r in prices)


def test_the_arabic_name_is_the_menus_word_not_the_teasers():
    """The two lists disagree, in Arabic only: the content menu says «المقاوم
    للكبريتات» and the teaser button says «المقاوم». The menu wins because its
    wording is the one the family page's own <h1> agrees with — so this asserts
    a CHOICE, and it breaks if the parse order is ever flipped."""
    prices, _w, _e, _f = crawl()
    sr = {r["category_path_ar"] for r in prices
          if r["category_path"] == "Sulphate Resistant"}

    assert sr == {"المقاوم للكبريتات"}
    assert "المقاوم" in _page("/ar/our_products_ar")     # the teaser's word is really there


def test_the_ruled_paths_are_the_pairs_the_site_itself_declares():
    """The ruling maps a designation to two paths, one per language. Neither is
    derived from the other — `/en/suez-opc` and `/ar/suez-42.5-n` share no stem
    — so each pair is checked against the family page's own
    `<link rel="alternate" hreflang>` and `<link rel="canonical">`."""
    evidence = json.loads((LIVE / FAMILIES_EVIDENCE).read_text(encoding="utf-8"))
    declared = {f["en"]["canonical"]: f["en"]["alternate"]["ar"] for f in evidence}
    declared = {en[len(CORPORATE):]: ar[len(CORPORATE):] for en, ar in declared.items()}

    for designation, (en_path, ar_path) in _FAMILY_BY_DESIGNATION.items():
        assert en_path in declared, f"{designation}: {en_path} is no family page"
        assert declared[en_path] == ar_path, (
            f"{designation}: the site pairs {en_path} with {declared[en_path]}, "
            f"not {ar_path}")


def test_the_family_page_states_the_designation_the_ruling_rests_on():
    """The ruling is only defensible because the corporate site prints a
    designation under each family's <h1>. If a page stops stating one, the
    evidence for that row of the table is gone and someone must look again."""
    evidence = json.loads((LIVE / FAMILIES_EVIDENCE).read_text(encoding="utf-8"))
    by_path = {f["en"]["canonical"][len(CORPORATE):]: f for f in evidence}

    assert by_path["/en/suez-opc"]["en"]["designation"] == "CEMII / A-P 42,5N"
    assert by_path["/en/sulphate-resistant"]["en"]["designation"] == "CEM IV/A (P) 42.5 SR"
    assert by_path["/en/helwan-oasis"]["en"]["designation"] == "OASIS 22.5X"
    assert by_path["/en/cem-iii"]["en"]["designation"] == "CEM III / A 42,5N"
    # The designation is the SAME Latin string in both languages, exactly as
    # the store stores productLabelEn == productLabelAr. That is why it is a
    # designation and not a name, and why it is not the category.
    for family in evidence:
        assert (family["en"]["designation"].split()
                == family["ar"]["designation"].split()), family["en"]["h1"]
    # …split() rather than ==, for ONE reason, recorded rather than smoothed
    # away: the Bulk page's Arabic designation separates CEMI from 42.5 with a
    # NON-BREAKING space (U+00A0) where its English uses U+0020. The other four
    # are byte-identical. It is a typographic wart in the site's own CMS, it
    # does not make the string a translation, and it reaches no row — Bulk is
    # the one family with no store product. Asserted so that the day someone
    # fixes it, this says so instead of going quietly green.
    bulk = next(f for f in evidence if f["en"]["h1"] == "Bulk Cement")
    assert bulk["en"]["designation"] == "CEMI 42.5 N"
    assert bulk["ar"]["designation"] == "CEMI 42.5 N"


def test_the_bulk_family_has_no_store_product_and_that_agrees_with_the_store():
    """The corporate site publishes five families; the store sells four of them.
    `/api/ProductTypes` carries a `Bulk`/«سائب» type NO product uses, so both
    hosts say bulk is not sold online — which is why the fifth family being
    absent from every row is a cross-check and not a gap."""
    prices, _w, _e, _f = crawl()
    assert "Bulk Cement" not in {r["category_path"] for r in prices}
    assert "أسمنت سائب" not in {r["category_path_ar"] for r in prices}
    # The store's own side of the agreement: one packaging value, on all 9.
    assert {p["productTypes"]["productTypeNameEn"] for p in _fixture("Products")} == {
        PACKAGING}


def test_a_designation_nobody_ruled_on_gets_no_category_and_says_so():
    """The standing ASK rule, applied to the category. A new cement must arrive
    uncategorised and NAMED, not filed under whichever family looks closest."""
    products = copy.deepcopy(_fixture("Products"))
    for product in products:
        if product["id"] == HELWAN_SINGLE:
            product["productLabelEn"] = "CEM V/A (S-P) 32,5N MOON BASE"

    prices, warnings, _e, _f = crawl(_StubFetcher({"Products": products}))
    orphaned = [r for r in prices if r["external_product_id"] == HELWAN_SINGLE]

    assert orphaned, "the product must still be priced — only its category is unknown"
    assert all(r["category_path"] == "" and r["category_path_ar"] == ""
               for r in orphaned)
    assert any("no ruled family" in w and "MOON BASE" in w for w in warnings)
    # The other seven are untouched: one unknown cement is not a source-wide loss.
    assert all(r["category_path"] for r in prices
               if r["external_product_id"] != HELWAN_SINGLE)


def test_a_renamed_family_page_empties_the_category_and_says_so():
    """The ruling names a path. If the listing stops naming that path — renamed,
    moved, retired — the category cannot be read and must not be invented."""
    moved = _page("/en/our-products").replace("/en/sulphate-resistant",
                                              "/en/sulphate-resistant-v2")

    prices, warnings, _e, _f = crawl(_StubFetcher(pages={"/en/our-products": moved}))
    lost = [r for r in prices if not r["category_path"]]

    assert lost, "the SR products must lose their category when the path moves"
    assert any("no longer names the family page" in w for w in warnings)
    # Only the SR family is affected — 33 of the 108 rows, the three SR products
    # — and the other three families still read their own names.
    assert len(lost) == 33
    assert {r["category_path"] for r in prices if r["category_path"]} == {
        "Suez, Helwan, Tourah", "Suez Oasis, Helwan Oasis", "Blast Furnace Cement"}
    # And nothing fell back to the packaging type on the way down.
    assert PACKAGING not in {r["category_path"] for r in prices}
    assert PACKAGING_AR not in {r["category_path_ar"] for r in prices}


def test_a_down_host_reports_one_defect_not_a_rename_for_every_product():
    """The defect names the host once. Eight 'renamed' warnings beneath it would
    describe that same one fact nine times — and would send someone hunting for
    a rename that never happened."""
    down = _StubFetcher(pages={"/en/our-products": None, "/ar/our_products_ar": None})
    _p, warnings, _e, _f = crawl(down)

    assert not any("no longer names the family page" in w for w in warnings)
    assert not any("no ruled family" in w for w in warnings)


def test_the_corporate_host_being_down_is_a_defect_not_a_quiet_fallback():
    """A DEFECT, because the category is a fact this source does publish and a
    run without it produced degraded data. And emphatically NOT a fallback to
    the packaging type — putting «معبأ» back on a bad day is how the confusion
    this reader removes would return."""
    fetcher = _StubFetcher(pages={"/en/our-products": None, "/ar/our_products_ar": None})
    entry = make_entry()
    prices, warnings, _e, _f = crawl(fetcher, entry)

    assert len(prices) == 108, "the prices are on another host and must survive"
    assert all(r["category_path"] == "" and r["category_path_ar"] == ""
               for r in prices)
    assert PACKAGING not in {r["category_path"] for r in prices}

    defects = defects_of(_StubFetcher(pages={"/en/our-products": None,
                                             "/ar/our_products_ar": None}), entry)
    assert len(defects) == 2
    assert any("/en/our-products" in d for d in defects)
    assert any("/ar/our_products_ar" in d for d in defects)


def test_one_language_down_never_lets_the_other_stand_in_for_it():
    """The Arabic listing failing must empty the Arabic column, not fill it with
    English. A half-read taxonomy is the case where a silent fallback would be
    least visible and most wrong."""
    entry = make_entry()
    prices, _w, _e, _f = crawl(_StubFetcher(pages={"/ar/our_products_ar": None}), entry)

    assert all(r["category_path"] for r in prices)          # English still reads
    assert all(r["category_path_ar"] == "" for r in prices)  # Arabic is empty, not English
    assert defects_of(_StubFetcher(pages={"/ar/our_products_ar": None}), entry)


def test_without_a_taxonomy_block_the_category_is_empty_and_no_host_is_guessed():
    """A source with no taxonomy: declared, so it costs no request and invents
    no host. The prices are unaffected."""
    entry = make_entry(taxonomy=None)
    prices, _w, _e, fetcher = crawl(entry=entry)

    assert len(prices) == 108
    assert all(r["category_path"] == "" for r in prices)
    assert fetcher.requests_count == 3
    assert not any(url.startswith(CORPORATE) for url in fetcher.asked)


# ---- the packaging type: kept, and still awaiting a ruling -------------------

def test_the_packaging_type_is_kept_as_a_detail_in_both_languages():
    """It stopped being a category; it did not stop being true. The store
    publishes it in both languages — unlike the designation — so both are kept."""
    _p, _w, enrichment, _f = crawl()
    filed = {(r["attribute_code"], r["lang"]): r for r in enrichment
             if r["attribute_code"].startswith("packaging_type")}

    assert filed[("packaging_type", "en")]["raw_value"] == PACKAGING
    assert filed[("packaging_type_ar", "ar")]["raw_value"] == PACKAGING_AR
    assert filed[("packaging_type", "en")]["attribute_label"] == "Packaging type"
    # One pair per priced product, so nothing was lost in the move.
    assert sum(1 for r in enrichment if r["attribute_code"] == "packaging_type") == 8
    assert sum(1 for r in enrichment if r["attribute_code"] == "packaging_type_ar") == 8


def test_the_packaging_group_is_reported_unruled_rather_than_chosen():
    """The standing ASK rule (vocab.DetailGroup rule 4). `packaging_type` is
    deliberately NOT in _DETAIL_GROUP_BY_CODE: the owner was asked on 2026-07-30
    and called for two studies first, so the fallback holds it and the crawl says
    so. Whoever files it puts the answer in the map — and this test is what tells
    them to delete it when they do."""
    assert group_for_code("packaging_type") == (DetailGroup.MORE_INFORMATION, False)
    assert group_for_code("packaging_type_ar") == (DetailGroup.MORE_INFORMATION, False)

    _p, warnings, _e, _f = crawl()
    assert any("does not recognise" in w and "packaging_type" in w for w in warnings)


def test_the_designation_stays_the_record_and_is_not_copied_into_the_category():
    """cement_type is the RECORD: per product, plant encoded inside it, the
    store's own string. The category is DERIVED — the family that designation
    belongs to — and holds a different string in each language. Neither column
    repeats the other, which is the whole reason both can exist."""
    prices, _w, enrichment, _f = crawl()
    designations = {r["external_product_id"]: r["raw_value"] for r in enrichment
                    if r["attribute_code"] == "cement_type"}

    assert designations[SUEZ_MULTI] == "CEMII / A-P 42,5N SUEZ"
    for row in prices:
        designation = designations[row["external_product_id"]]
        assert row["category_path"] != designation
        assert row["category_path_ar"] != designation
    # Exactly one row per product states the designation, and it is English-only
    # because the store holds the same Latin string in productLabelAr.
    assert len(designations) == 8
    assert not [r for r in enrichment if r["attribute_code"] == "cement_type_ar"]


# ---- the shapes that must fail loud ------------------------------------------

def test_the_embedded_product_copy_is_not_what_the_plant_rule_reads():
    """Every price row carries a full copy of its product — the reason the body
    is 19 MB — and that copy's `plants` is null on all 2,070 rows. A connector
    reading it instead of joining on productId would see no plantCode and emit
    nothing for the 6 non-multi-plant products."""
    table = copy.deepcopy(_fixture("ProductsPrices"))
    by_id = {p["id"]: p for p in _fixture("Products")}
    for row in table:
        row["products"] = {**by_id[row["productId"]], "plants": None}

    prices, _w, _e, _f = crawl(_StubFetcher({"ProductsPrices": table}))
    assert len(prices) == 108


def test_a_price_naming_an_unknown_product_is_skipped_out_loud():
    table = copy.deepcopy(_fixture("ProductsPrices"))
    for row in table:
        if row["productId"] == HELWAN_SINGLE:
            row["productId"] = "00000000-0000-0000-0000-000000000000"

    prices, warnings, _e, _f = crawl(_StubFetcher({"ProductsPrices": table}))
    assert not [r for r in prices if r["external_product_id"] == HELWAN_SINGLE]
    assert any("absent from /api/Products" in w for w in warnings)


def test_a_response_that_is_not_an_array_fails_loud_never_as_zero_rows():
    """`data.get("products")` returning None once made a sibling connector print
    "0 rows" as a success while the site was up the whole time."""
    with pytest.raises(ValueError, match="did not answer a JSON array"):
        crawl(_StubFetcher({"Products": {"error": "nope"}}))


# ---- enrichment --------------------------------------------------------------

def test_the_four_technical_blocks_are_filed_where_the_owner_ruled():
    """None of these four codes was in _DETAIL_GROUP_BY_CODE, so group_for_code
    reported them unrecognised and the standing ASK rule fired. Owner ruling
    2026-07-29: all four under Specifications — each states a property of the
    cement itself. They are in the map now, so nothing files by fallback."""
    for code in ("physical_characteristics", "chemical_characteristics",
                 "characteristics", "applications"):
        assert group_for_code(code) == (DetailGroup.SPECIFICATIONS, True)
        assert group_for_code(f"{code}_ar") == (DetailGroup.SPECIFICATIONS, True)

    _p, warnings, enrichment, _f = crawl()
    # These four are in the map, so none of them appears in the unrecognised
    # report. `packaging_type` DOES appear there and deliberately so — see
    # test_the_packaging_group_is_reported_unruled_rather_than_chosen — which is
    # why this checks the four codes rather than the absence of any warning.
    unrecognised = " ".join(w for w in warnings if "does not recognise" in w)
    for code in ("physical_characteristics", "chemical_characteristics",
                 "characteristics", "applications"):
        assert code not in unrecognised
    filed = {r["attribute_code"]: r["attribute_group"] for r in enrichment}
    assert filed["applications"] == DetailGroup.SPECIFICATIONS.value
    assert filed["chemical_characteristics_ar"] == DetailGroup.SPECIFICATIONS.value
    assert filed["description"] == DetailGroup.DESCRIPTION.value
    assert filed["manufacturer_ar"] == DetailGroup.MORE_INFORMATION.value


def test_the_technical_blocks_are_stored_as_text_not_as_markup():
    """The site renders them through innerHTML, so the markup is a rendering
    instruction and the sentences are the fact."""
    _p, _w, enrichment, _f = crawl()
    physical = next(r for r in enrichment if r["external_product_id"] == SUEZ_MULTI
                    and r["attribute_code"] == "physical_characteristics")
    assert "<p>" not in physical["raw_value"]
    assert "Initial setting time" in physical["raw_value"]
    assert "\n" in physical["raw_value"]   # one line per <p>, not a run-on


def test_enrichment_rides_the_products_response_and_costs_no_request():
    """15 facts, not 13: the packaging type moved here from category_path and it
    is bilingual, so each product gained two rows. Still zero extra requests —
    the two corporate ones are the taxonomy, not the details."""
    _p, _w, enrichment, fetcher = crawl()
    assert len(enrichment) == 120            # 8 priced products x 15 stated facts
    assert fetcher.requests_count == 5
    # Exactly once, and it is the join the prices already needed. Compared on
    # the endpoint NAME, not by substring: "/api/ProductsPrices" contains
    # "/api/Products".
    assert [url.rsplit("/", 1)[-1] for url in fetcher.asked].count("Products") == 1


def test_a_product_nothing_prices_states_its_details_to_nobody_and_says_so():
    """Ingest refuses an attribute whose product it never registered — it learns
    a product from its PRICE row. Emitting details for an unpriced product would
    be rejects on every crawl for as long as it stays unpriced, so the connector
    names the product instead."""
    prices, warnings, enrichment, _f = crawl()

    assert TOURAH_UNPRICED not in {r["external_product_id"] for r in prices}
    assert TOURAH_UNPRICED not in {r["external_product_id"] for r in enrichment}
    assert any("catalogued with no price in any city (Tourah)" in w for w in warnings)


def test_enrichment_is_emitted_only_when_the_manifest_asks_for_it():
    entry = make_entry(extract=[ExtractSpec(kind=ExtractKind.PRODUCT_PRICES,
                                            scope=ExtractScope.CENSUS)])
    prices, _w, enrichment, _f = crawl(entry=entry)
    assert len(prices) == 108 and enrichment == []


# ---- the warehouse -----------------------------------------------------------

def test_heidelberg_end_to_end_into_warehouse():
    """108 prices for 8 products must land as 108 INDEPENDENT offers. If they
    collapsed onto one variant they would read as a single offer changing price
    108 times inside one crawl — the oscillation the variant key prevents."""
    entry = make_entry()
    tables = list(HeidelbergPriceMatrixConnector(_StubFetcher()).fetch(entry))
    conn: sqlite3.Connection = dbmod.connect(":memory:")
    try:
        dbmod.migrate(conn)
        result = ingest_payloads(conn, entry, [t.to_payload() for t in tables])
        offers = conn.execute("SELECT COUNT(*) FROM source_offer").fetchone()[0]
        variants = conn.execute("SELECT COUNT(*) FROM source_variant").fetchone()[0]
        products = conn.execute("SELECT COUNT(*) FROM source_product").fetchone()[0]
    finally:
        conn.close()

    assert result.observations == 108 and not result.errors
    assert (variants, offers) == (108, 108)
    # 8, not 9: the ninth is priced nowhere, so no row registers it — and its
    # details are withheld for the same reason rather than arriving as rejects.
    assert (products, result.rejected_out_of_scope) == (8, 0)
