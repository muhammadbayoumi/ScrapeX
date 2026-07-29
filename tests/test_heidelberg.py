"""T2: heidelberg-price-matrix — the three filters that turn 211 numbers into
the 108 prices the storefront can actually render, plus the api-host split.

Every fixture is a live capture of 2026-07-29; see
tests/fixtures/live/heidelberg_2026-07-29.CAPTURE.md for what was fetched, what
was trimmed and the census the trim preserves.
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
    HeidelbergPriceMatrixConnector, _api_root, _price)
from scrapex.ingest import ingest_payloads
from scrapex.rowspec import ENRICHMENT, PRODUCT_PRICES, RowView
from scrapex.vocab import DetailGroup, ExtractKind, ExtractScope, group_for_code

LIVE = Path(__file__).parent / "fixtures" / "live"
_FILES = {
    "Products": "heidelberg_products_2026-07-29.json",
    "Plants": "heidelberg_plants_2026-07-29.json",
    "ProductsPrices": "heidelberg_products_prices_2026-07-29.json",
}

# Anchors read out of the capture, so a test says WHICH product it means.
SUEZ_MULTI = "1000007e-32a9-4324-8ed9-117b0c47389f"     # isMultiPlant, own plant Y210
HELWAN_SINGLE = "4ce38978-903b-4a28-9aec-f3498c38f990"  # isMultiPlant false, own plant Y410
# Cairo prices both of them at the same six figures, which is what makes the
# pair a clean test of the plant rule and of nothing else.
CAIRO = "e46739d4-31a5-420a-b540-a6d859fb6cd6"
DAHAB = "eab70d2e-b602-442f-bfd1-08dac8c1d154"
# The one product no city prices: catalogued, active, and quoted nowhere.
TOURAH_UNPRICED = "6217a245-4758-4ca3-b19a-ae83eb4ad347"


def _fixture(name: str):
    return json.loads((LIVE / _FILES[name]).read_text(encoding="utf-8"))


class _Resp:
    def __init__(self, payload): self._payload = payload
    def json(self): return self._payload


class _StubFetcher:
    """Serves the three captured tables by endpoint name."""

    def __init__(self, tables: dict | None = None):
        self.requests_count = 0
        self.asked: list[str] = []
        self._tables = tables or {}

    def get(self, url, **kwargs):
        self.requests_count += 1
        self.asked.append(url)
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


# ---- the split host ---------------------------------------------------------

def test_the_data_host_is_the_api_one_never_the_storefront():
    """The storefront serves static files and 404s every API path. This is the
    single reason custom-json-api cannot serve this source: it composes
    f"{source.base_url}/api/products" and never reads source.api."""
    assert _api_root(make_entry()) == "https://onlinestoreapi.heidelbergmaterials.eg/api"


def test_without_the_api_host_it_refuses_rather_than_guesses():
    with pytest.raises(ValueError, match="needs api.base_url"):
        _api_root(make_entry(api=None))


def test_the_whole_source_is_three_requests():
    """Two tables would do it if any product were assigned to Y220. None is —
    all 9 sit on Y210 or Y410 — so /api/Plants is what makes «القطامية»
    the site's word rather than our transliteration."""
    _prices, _w, _e, fetcher = crawl()
    assert fetcher.requests_count == 3
    assert [url.rsplit("/", 1)[-1] for url in fetcher.asked] == [
        "Products", "Plants", "ProductsPrices"]


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
    assert (row["category_path"], row["category_path_ar"]) == ("Bagged", "معبأ")


def test_the_product_link_is_the_client_side_route_and_is_never_fetched():
    """/productinfo/{guid} 404s at IIS — there is no SPA fallback rewrite. It is
    recorded for a human to open, and the crawl must never follow it."""
    prices, _w, _e, fetcher = crawl()
    assert prices[0]["product_link"] == (
        "https://onlinestore.heidelbergmaterials.eg/productinfo/"
        + prices[0]["external_product_id"])
    assert not any("/productinfo/" in url for url in fetcher.asked)


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
    assert not any("does not recognise" in w for w in warnings)
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
    _p, _w, enrichment, fetcher = crawl()
    assert len(enrichment) == 104            # 8 priced products x 13 stated facts
    assert fetcher.requests_count == 3


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
