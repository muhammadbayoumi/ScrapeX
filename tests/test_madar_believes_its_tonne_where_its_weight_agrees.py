"""«يباع بالطن»: the unit madar states in words, believed where its weight agrees.

On 2026-07-29 madar wrote «طن» nowhere a crawl could reach, and its rebar read
"/ 1,000 kg" against an empty Unit column. By the crawl of 2026-10-25 its own
Arabic descriptions said «يباع بالطن» or «يسعر بالطن» on 22 products, and the
owner ruled on 2026-10-26: «وحدة الحديد طن كالموقع» — the unit is the tonne, as
the site says (#1833).

THE SITE DISAGREES WITH ITSELF ON ONE OF THE 22. Its steel mesh says «يباع بالطن»
too, and is priced per sheet: 24 to 199 SAR for sheets of 5.9 to 61.7 kg. So the
sentence alone is not enough, and the charter asks the weight first:

    143 offers state weight 1000 kgs  -> tonne (18 rebar, 3 steel-coil products)
     19 offers weigh one sheet each    -> no unit, as the raw-facts rule requires

Every value below is the shop's, read off his warehouse (v26, mode=ro) and the
live pages on 2026-10-26.
"""

from __future__ import annotations

import json

import pytest

from pydantic import ValidationError

from scrapex.config import (MANIFEST_FILE, ExtractSpec, SourceEntry, UnitWitness,
                            load_manifest)
from scrapex.connectors.magento import MagentoGraphqlConnector, _apply_charter
from scrapex.rowspec import PRODUCT_PRICES, RowView
from scrapex.units import Charter
from scrapex.vocab import ExtractKind, ExtractScope

_REBAR_SENTENCE = ("حديد تسليح تعمير: حديد تسليح مضلع حسب مواصفة ASTM A615، "
                   "يباع بالطن بأطوال 12 متر.")
_PRICED_SENTENCE = "المقاولون: يسعر بالطن ويوصل للموقع بأسطول مدار."


@pytest.fixture(scope="module")
def madar() -> Charter:
    entry = load_manifest(MANIFEST_FILE).get("MADAR")
    return Charter(json.loads(entry.unit_charter.model_dump_json()))


def _fields(**over) -> dict:
    base = {"weight": "", "weight_unit": "", "variant_axes": "", "variant_axes_ar": "",
            "product_name": "", "product_name_ar": "", "spec_size": "",
            "description_ar": ""}
    base.update(over)
    return base


# ---- the charter -------------------------------------------------------------

def test_the_sentence_and_the_weight_together_make_a_tonne(madar):
    r = madar.resolve(_fields(description_ar=_REBAR_SENTENCE,
                              weight="1000", weight_unit="kgs"))

    assert r is not None and (r.unit, r.quantity) == ("tonne", 1.0)
    assert r.provenance == "stated_in_prose"
    # The shop's own words are the raw reading, so the details can show them.
    assert (r.raw, r.raw_lang) == ("يباع بالطن", "ar")
    # The witness names the rules that authorised it AND the agreeing weight.
    assert r.witness.startswith("description_ar@ar/v2: يباع بالطن")
    assert "1000" in r.witness


def test_priced_by_the_tonne_says_the_same_thing(madar):
    r = madar.resolve(_fields(description_ar=_PRICED_SENTENCE,
                              weight="1000", weight_unit="kgs"))
    assert r is not None and r.unit == "tonne"


def test_the_mesh_says_tonne_and_its_weight_refuses_it(madar):
    """THE CASE THE CONFIRMATION EXISTS FOR. «شبك حديد صبة» 10404154020 weighs
    5.918 kg and costs 24.15: one sheet's price. Its description's «بالطن»
    describes the steel, not what the price buys."""
    assert madar.resolve(_fields(description_ar="شبك حديد صبة يباع بالطن",
                                 weight="5.918", weight_unit="kgs")) is None


def test_a_weight_alone_is_still_not_a_unit(madar):
    """#84's measured ruling stands: across 6,764 observations price ÷ weight
    ran to 38,923, so `weight` is a basis for some products and a piece's mass
    for others. 1000 kgs with no sentence names nothing."""
    assert madar.resolve(_fields(weight="1000", weight_unit="kgs")) is None


def test_a_weight_whose_unit_the_store_will_not_state_confirms_nothing(madar):
    assert madar.resolve(_fields(description_ar=_REBAR_SENTENCE,
                                 weight="1000", weight_unit="")) is None


def test_a_text_that_names_two_units_is_the_shop_disagreeing_with_itself(madar):
    """Silence, never whichever sentence happened to come first."""
    both = "يباع بالطن. ويباع بالحبة للكميات الصغيرة."
    assert madar.resolve(_fields(description_ar=both,
                                 weight="1000", weight_unit="kgs")) is None


def test_a_unit_the_owner_has_not_ruled_on_is_refused(madar):
    """The same descriptions say «يباع بالمتر» on 125 offers and «بالقطعة» on
    65. Those are his to rule on; only the tonne is admitted."""
    assert madar.resolve(_fields(description_ar="شريط حواف يباع بالمتر",
                                 weight="1000", weight_unit="kgs")) is None


def test_a_list_of_possible_units_is_not_a_statement(madar):
    """Read verbatim off the rebar page: a sentence that names the tonne among
    three units states none of them for this product."""
    general = "الأسعار حسب الوحدة الموضحة (طن أو متر مكعب أو حبة)؛ اطلب عرض سعر."
    assert madar.resolve(_fields(description_ar=general,
                                 weight="1000", weight_unit="kgs")) is None


def test_the_variants_own_statement_still_answers_first(madar):
    """Ranked after every field witness: an option value the shop states for
    THIS variant outranks a sentence about the product."""
    r = madar.resolve(_fields(description_ar=_REBAR_SENTENCE, weight="1000",
                              weight_unit="kgs",
                              variant_axes_ar='{"المقاس":"4 كجم/صندوق"}'))
    assert r is not None and r.unit == "box"


# ---- the connector hands the description to the charter --------------------

def _row(**over) -> list[str]:
    row = [""] * len(PRODUCT_PRICES.columns)
    for key, value in over.items():
        row[PRODUCT_PRICES.columns.index(key)] = value
    return row


def test_the_connector_reads_the_products_own_description(madar):
    """The description arrives as Page Builder HTML; the charter reads the
    text madar's description_ar row stores, not the markup."""
    product = {"description": {"html": f"<style>#x{{}}</style><p>{_REBAR_SENTENCE}</p>"}}
    row = _row(weight="1000", weight_unit="kgs")

    _apply_charter(row, madar, product)

    at = PRODUCT_PRICES.columns.index
    assert row[at("unit")] == "tonne"
    assert row[at("basis_quantity")] == "1"
    assert row[at("unit_basis_provenance")] == "stated_in_prose"
    assert row[at("selling_unit_raw")] == "يباع بالطن"


def test_a_product_without_a_description_is_left_as_it_was(madar):
    row = _row(weight="1000", weight_unit="kgs")
    _apply_charter(row, madar, {})
    _apply_charter(row, madar, None)
    assert row[PRODUCT_PRICES.columns.index("unit")] == ""


# ---- end to end: the crawl's own rows ----------------------------------------

def _member(uid, sku, name, weight, price, decimal, minimum, step):
    return {"uid": uid, "sku": sku, "name": name, "stock_status": "IN_STOCK",
            "weight": weight, "is_qty_decimal": decimal, "min_sale_qty": minimum,
            "qty_increments": step, "only_x_left_in_stock": None,
            "price_range": {"minimum_price": {"regular_price": {"value": price},
                                              "final_price": {"value": price}}}}


_REBAR = {
    "__typename": "GroupedProduct", "uid": "VEFN", "sku": "10128-TSS",
    "url_key": "tameer-steel-rebar", "name": "حديد تسليح تعمير",
    "stock_status": "IN_STOCK", "categories": [],
    "description": {"html": f"<p>{_REBAR_SENTENCE}</p>"},
    "price_range": {"minimum_price": {"regular_price": {"value": 3199.88},
                                      "final_price": {"value": 3199.88}},
                    "maximum_price": {"final_price": {"value": 3199.88}}},
    "items": [{"qty": 0, "position": 1, "product": _member(
        "VDEy", "101281212", "حديد تسليح تعمير | 12مم × 12متر | ASTM A615 جريد 60",
        1000, 3199.88, True, 0.25, 0.05)}],
}

_MESH = {
    "__typename": "ConfigurableProduct", "uid": "U1JN", "sku": "10400-SRM",
    "url_key": "steel-reinforcing-mesh", "name": "شبك حديد صبة",
    "stock_status": "IN_STOCK", "categories": [],
    "description": {"html": "<p>شبك حديد تسليح ملحوم، يباع بالطن.</p>"},
    "price_range": {"minimum_price": {"regular_price": {"value": 24.15},
                                      "final_price": {"value": 24.15}},
                    "maximum_price": {"final_price": {"value": 24.15}}},
    # The axes as his warehouse stores them on 2026-10-26: the unit is in the
    # axis NAME and the value is a bare number, so no axis states a unit.
    "configurable_options": [{"attribute_code": "diameter_mm", "label": "القطر (مم)"},
                             {"attribute_code": "length_meters", "label": "الطول (متر)"}],
    "variants": [{"attributes": [{"code": "diameter_mm", "label": "4"},
                                 {"code": "length_meters", "label": "4"}],
                  "product": _member("U1JNNA==", "10404154020",
                                     "شبك حديد صبة - 4.00ملم * 1.5 * 4.0متر - 20*20سم",
                                     5.918, 24.15, True, 1, 1)}],
}


class _Response:
    def __init__(self, payload): self._payload = payload
    def json(self): return self._payload


class _Fetcher:
    """storeConfig answers "kgs", as madar's does on both store views."""

    def post(self, url, json=None, **kwargs):
        query = (json or {}).get("query", "")
        page = (json or {}).get("variables", {}).get("currentPage", 1)
        empty = {"data": {"products": {"items": [],
                                       "page_info": {"current_page": 1, "total_pages": 1}}}}
        if "storeConfig" in query:
            return _Response({"data": {"storeConfig": {"weight_unit": "kgs"}}})
        if "categoryList" in query:
            return _Response({"data": {"categoryList": [{"children": []}]}})
        if (kwargs.get("headers") or {}).get("Store") or "category_uid" in query or page != 1:
            return _Response(empty)
        return _Response({"data": {"products": {
            "page_info": {"current_page": 1, "total_pages": 1},
            "items": [_REBAR, _MESH]}}})

    def close(self): pass


def _crawl() -> dict[str, dict]:
    charter = load_manifest(MANIFEST_FILE).get("MADAR").unit_charter
    entry = SourceEntry.model_validate(dict(
        source_key="MADAR", source_name="المدار", base_url="https://www.madar.com",
        family="magento-graphql", currency="SAR", default_region="SA", vat_mode="incl",
        extract=[ExtractSpec(kind=ExtractKind.PRODUCT_PRICES, scope=ExtractScope.CENSUS)],
        unit_charter=charter.model_dump()))
    tables = [t for t in MagentoGraphqlConnector(_Fetcher()).fetch(entry)
              if t.kind == ExtractKind.PRODUCT_PRICES]
    view = RowView(PRODUCT_PRICES, tables[0].header)
    return {r["external_sku"]: r for t in tables for r in map(view.as_dict, t.rows)}


def test_the_crawl_states_the_rebar_in_tonnes_and_leaves_the_mesh_unitless():
    rows = _crawl()

    rebar = rows["101281212"]
    assert (rebar["unit"], rebar["basis_quantity"]) == ("tonne", "1")
    assert rebar["unit_basis_provenance"] == "stated_in_prose"
    # The price and the shop's quantity facts are untouched.
    assert rebar["minimum_quantity"] == "0.25" and rebar["quantity_increment"] == "0.05"

    mesh = rows["10404154020"]
    assert mesh["unit"] == "" and mesh["basis_quantity"] == ""


# ---- a charter that cannot say what it reads is refused at validation --------

def test_a_sold_by_witness_must_name_its_phrases_and_units():
    """Without them it would read any word after any verb as a unit."""
    with pytest.raises(ValidationError, match="phrases and the units"):
        UnitWitness(field="description_ar", shape="sold_by")
    with pytest.raises(ValidationError, match="phrases and the units"):
        UnitWitness(field="description_ar", shape="sold_by", phrases=["يباع بال"])


def test_sold_by_settings_on_another_witness_are_refused():
    """A typo that put `confirm` on a quantity witness would otherwise be a
    rule that silently never runs."""
    with pytest.raises(ValidationError, match="belong to a sold_by witness"):
        UnitWitness(field="spec_size", shape="quantity", phrases=["يباع بال"])
    with pytest.raises(ValidationError, match="belong to a sold_by witness"):
        UnitWitness(field="spec_size", confirm={"field": "weight", "unit_field": "weight_unit",
                                                "quantity": 1000, "unit": "kg"})
