"""«يباع بالطن»: the unit madar states in words, believed where its weight agrees.

On 2026-07-29 madar wrote «طن» nowhere a crawl could reach, and its rebar read
"/ 1,000 kg" against an empty Unit column. By the crawl of 2026-10-25 its own
Arabic descriptions said «يباع بالطن» or «يسعر بالطن» on 22 products, and the
owner ruled on 2026-10-26: «وحدة الحديد طن كالموقع» — the unit is the tonne, as
the site says (#1833).

THE SITE DISAGREES WITH ITSELF ON ONE OF THE 22. Its steel mesh carries «يسعر
بالطن» too, in its line about contractors, and is priced per sheet: 24 to 199 SAR
for sheets of 5.9 to 61.7 kg. So the sentence alone is not enough, and the charter
asks the weight first:

    143 offers state weight 1000 kgs  -> tonne (18 rebar, 3 steel-coil products)
     19 offers weigh one sheet each    -> no unit, as the raw-facts rule requires

The sentences and figures below are the shop's, read off his warehouse (v26,
mode=ro), except the markup and the disagreement built to test those cases.
"""

from __future__ import annotations

import copy
import json
import re

import pytest
from pydantic import ValidationError

from scrapex import db as dbmod
from scrapex import reports
from scrapex.config import MANIFEST_FILE, UnitCharter, UnitWitness, load_manifest
from scrapex.connectors.magento import GraphqlRefused, MagentoGraphqlConnector, _apply_charter
from scrapex.ingest import ingest_payloads
from scrapex.payload import new_payload
from scrapex.rowspec import PRODUCT_PRICES, RowView
from scrapex.units import Charter
from scrapex.vocab import ExtractKind

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
    # The witness names the rules that authorised it AND the agreeing weight, in
    # the shop's own words, which is what lets a reading be traced to both.
    assert r.witness == "description_ar@ar/v2: يباع بالطن (with weight 1000 kgs)"


def test_priced_by_the_tonne_says_the_same_thing(madar):
    r = madar.resolve(_fields(description_ar=_PRICED_SENTENCE,
                              weight="1000", weight_unit="kgs"))
    assert r is not None and r.unit == "tonne"


def test_both_sentences_in_one_description_are_one_statement(madar):
    """The commonest real text: 15 of the 22 products, 79 of the 143 offers, say
    both. One unit named twice is no disagreement, and the raw reading is whichever
    the shop wrote first."""
    r = madar.resolve(_fields(description_ar=f"{_REBAR_SENTENCE} {_PRICED_SENTENCE}",
                              weight="1000", weight_unit="kgs"))
    assert r is not None and r.unit == "tonne" and r.raw == "يباع بالطن"

    r = madar.resolve(_fields(description_ar=f"{_PRICED_SENTENCE} {_REBAR_SENTENCE}",
                              weight="1000", weight_unit="kgs"))
    assert r is not None and r.unit == "tonne" and r.raw == "يسعر بالطن"


def test_the_mesh_says_tonne_and_its_weight_refuses_it(madar):
    """THE CASE THE CONFIRMATION EXISTS FOR. «شبك حديد صبة» 10404154020 weighs
    5.918 kg and costs 24.15: one sheet's price. Its «يسعر بالطن» is a line about
    contractors, not what this price buys."""
    assert madar.resolve(_fields(description_ar=_PRICED_SENTENCE,
                                 weight="5.918", weight_unit="kgs")) is None


@pytest.mark.parametrize("weight", ["999", "1001", "1000000"])
def test_exactly_the_quantity_confirms_not_more_and_not_less(madar, weight):
    """96 MADAR offers outside the 22 products weigh over 1000. A check that only
    asked for at least 1000 would pass the sentence on any of them."""
    assert madar.resolve(_fields(description_ar=_REBAR_SENTENCE,
                                 weight=weight, weight_unit="kgs")) is None


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
    """The same descriptions say «يباع بالمتر» on 125 offers, 70 of them a cubic
    metre, and «بالقطعة» on 65. Those are his to rule on; only the tonne is admitted."""
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


def test_the_charter_reads_the_text_not_the_markup(madar):
    """The sentence must survive a tag inside it, and words only inside a <style>
    block are not the shop saying anything. Both turn on _clean being applied."""
    at = PRODUCT_PRICES.columns.index
    row = _row(weight="1000", weight_unit="kgs")
    _apply_charter(row, madar, {"description": {"html": "<p>يباع <strong>بالطن</strong> بأطوال</p>"}})
    assert row[at("unit")] == "tonne"

    row = _row(weight="1000", weight_unit="kgs")
    _apply_charter(row, madar, {"description": {"html": "<style>يباع بالطن</style><p>حديد</p>"}})
    assert row[at("unit")] == ""


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
    "description": {"html": f"<p>{_PRICED_SENTENCE}</p>"},
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
    """A store that answers only what it is asked. description goes out only when the
    query selects it, so a query that stops asking loses the sentence, as it would on
    the real crawl. storeConfig answers "kgs", as madar's does on both store views."""

    def __init__(self, weight_unit="kgs", items=None):
        self.weight_unit = weight_unit
        self.items = items if items is not None else [_REBAR, _MESH]
        self.asked_for_a_page = False

    def post(self, url, json=None, **kwargs):
        query = (json or {}).get("query", "")
        page = (json or {}).get("variables", {}).get("currentPage", 1)
        empty = {"data": {"products": {"items": [],
                                       "page_info": {"current_page": 1, "total_pages": 1}}}}
        if "storeConfig" in query:
            if isinstance(self.weight_unit, Exception):
                raise self.weight_unit
            return _Response({"data": {"storeConfig": self.weight_unit and {
                "weight_unit": self.weight_unit}}})
        if "categoryList" in query:
            return _Response({"data": {"categoryList": [{"children": []}]}})
        if (kwargs.get("headers") or {}).get("Store") or "category_uid" in query or page != 1:
            return _Response(empty)
        self.asked_for_a_page = True
        items = copy.deepcopy(self.items)
        if not re.search(r"(?<!short_)description\s*\{", query):
            for item in items:
                item.pop("description", None)
        return _Response({"data": {"products": {
            "page_info": {"current_page": 1, "total_pages": 1},
            "items": items}}})

    def close(self): pass


def _madar():
    """MADAR's real entry, so the crawl sends the query his crawl sends."""
    return load_manifest(MANIFEST_FILE).get("MADAR")


def _tables(fetcher=None):
    return [t for t in MagentoGraphqlConnector(fetcher or _Fetcher()).fetch(_madar())
            if t.kind == ExtractKind.PRODUCT_PRICES]


def _crawl() -> dict[str, dict]:
    tables = _tables()
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


# ---- a store that will not state its weight unit -------------------------------

@pytest.mark.parametrize("answer", ["", ConnectionError("store unreachable")],
                         ids=["blank", "raising"])
def test_a_store_that_will_not_state_its_weight_unit_runs_no_crawl(answer):
    """One side request failing must not read as the shop withdrawing the tonne from
    143 offers at once. It has happened: crawl_run 109, 2026-08-05, status success,
    first warning 'storeConfig published no weight_unit'. The run stops before page 1,
    with the reason on the job, and nothing moves."""
    fetcher = _Fetcher(weight_unit=answer)

    with pytest.raises(GraphqlRefused, match="unit of its weights"):
        _tables(fetcher)

    assert not fetcher.asked_for_a_page, "the refusal came after the catalogue was read"


def test_a_charter_that_confirms_on_nothing_keeps_crawling_without_it():
    """The refusal is for a charter that needs the answer. Any other source keeps the
    old rule: no basis this run, and a note saying so."""
    entry = _madar().model_copy(deep=True)
    entry.unit_charter.witnesses = [w for w in entry.unit_charter.witnesses
                                    if w.shape != "sold_by"]
    fetcher = _Fetcher(weight_unit="")

    tables = [t for t in MagentoGraphqlConnector(fetcher).fetch(entry)
              if t.kind == ExtractKind.PRODUCT_PRICES]

    assert fetcher.asked_for_a_page and tables
    assert any("weight_unit" in warning for t in tables for warning in t.warnings)


# ---- end to end: connector, warehouse, every surface ---------------------------

def _ingest(conn, tables, day):
    return ingest_payloads(conn, _madar(), [new_payload(
        source_key="MADAR", kind=ExtractKind.PRODUCT_PRICES, client="cli",
        scraped_at=f"2026-11-{day:02d}T10:00:00Z", source_url=t.source_url,
        header=t.header, rows=t.rows) for t in tables])


def _no_sentence() -> list[dict]:
    """His warehouse today: the same products before the crawl that reads the tonne."""
    items = copy.deepcopy([_REBAR, _MESH])
    for item in items:
        item["description"] = {"html": "<p>حديد</p>"}
    return items


@pytest.fixture()
def warehouse(tmp_path):
    conn = dbmod.connect(tmp_path / "w.db")
    dbmod.migrate(conn)
    yield conn
    conn.close()


def test_the_next_crawl_gives_the_rebar_its_tonne_on_the_same_offer(warehouse):
    """What his next crawl does, on the real schema. Same offer, so his price history
    stays. The rebar prints its stated unit and no inferred basis on every surface, and
    the mesh prints neither, on every surface."""
    conn = warehouse
    _ingest(conn, _tables(_Fetcher(items=_no_sentence())), day=1)
    sku_offer = dict(conn.execute(
        "SELECT sv.external_sku, so.offer_id FROM source_offer so "
        "JOIN source_variant sv ON sv.source_variant_id = so.source_variant_id"))
    before = conn.execute("SELECT unit_basis_provenance FROM source_offer").fetchall()
    assert all(row[0] is None for row in before), "the fixture already reads a unit"

    _ingest(conn, _tables(), day=2)

    after = dict(conn.execute(
        "SELECT sv.external_sku, so.offer_id FROM source_offer so "
        "JOIN source_variant sv ON sv.source_variant_id = so.source_variant_id "
        "WHERE so.status = 'active'"))
    assert after == sku_offer, "learning the tonne minted a second offer"
    assert conn.execute(
        "SELECT COUNT(*) FROM change_event WHERE change_type IN "
        "('price_increase', 'price_decrease')").fetchone()[0] == 0

    rebar, mesh = sku_offer["101281212"], sku_offer["10404154020"]
    for offer, unit, basis in ((rebar, "tonne", ""), (mesh, "", "")):
        identity = reports.offer_identity(conn, "MADAR", offer)
        assert (identity["unit"], identity["price_basis"]) == (unit, basis)

    browsed = {r["sku"]: r for r in reports.browse_observations(conn, "MADAR").rows}
    assert (browsed["101281212"]["unit"], browsed["101281212"]["price_basis"]) == ("tonne", "")
    assert (browsed["10404154020"]["unit"], browsed["10404154020"]["price_basis"]) == ("", "")

    payload = reports.table_payload(conn, "MADAR")
    drawn = {r["sku"]: r for r in payload["rows"]}
    assert (drawn["101281212"]["unit"], drawn["101281212"]["price_basis"]) == ("tonne", "")
    assert (drawn["10404154020"]["unit"], drawn["10404154020"]["price_basis"]) == ("", "")

    header, rows = reports.export_source_table(conn, "MADAR")
    exported = {r[header.index("sku")]: r for r in rows}
    for sku, unit in (("101281212", "tonne"), ("10404154020", "")):
        assert exported[sku][header.index("unit")] == unit
        assert exported[sku][header.index("price_basis")] == ""


# ---- a charter that cannot say what it reads is refused at validation --------

_CONFIRM = {"field": "weight", "unit_field": "weight_unit", "quantity": 1000, "unit": "kg"}


def test_a_sold_by_witness_must_name_its_phrases_and_units():
    """Without them it would read any word after any verb as a unit."""
    with pytest.raises(ValidationError, match="phrases and the units"):
        UnitWitness(field="description_ar", shape="sold_by", confirm=_CONFIRM)
    with pytest.raises(ValidationError, match="phrases and the units"):
        UnitWitness(field="description_ar", shape="sold_by", phrases=["يباع بال"],
                    confirm=_CONFIRM)


def test_a_sold_by_witness_must_name_what_confirms_it():
    """The mesh is why: the sentence alone would price a sheet by the tonne."""
    with pytest.raises(ValidationError, match="what confirms it"):
        UnitWitness(field="description_ar", shape="sold_by", phrases=["يباع بال"],
                    units=["tonne"])


def _charter(units=("tonne",), confirm_unit="kg", pack=("tonne", "kg")) -> dict:
    return {"witnesses": [{"field": "description_ar", "shape": "sold_by",
                           "phrases": ["يباع بال"], "units": list(units),
                           "confirm": {**_CONFIRM, "unit": confirm_unit}}],
            "scales": {"pack": list(pack)}}


@pytest.mark.parametrize("charter, says", [
    (_charter(units=("tonn",)), "tonn"),
    (_charter(confirm_unit="kilogram"), "kilogram"),
    (_charter(pack=("kg",)), "does not admit"),
], ids=["a unit no word maps to", "a confirming unit no word maps to", "a unit the pack refuses"])
def test_a_witness_that_could_never_fire_is_refused(charter, says):
    """Each of these resolves nothing on every row, exits 0 and passes every crawl in
    silence, so a ruling that depends on it simply would not happen."""
    with pytest.raises(ValidationError, match=says):
        UnitCharter.model_validate(charter)


def test_a_witness_that_can_fire_is_accepted():
    assert UnitCharter.model_validate(_charter()).witnesses[0].units == ["tonne"]


def test_sold_by_settings_on_another_witness_are_refused():
    """A typo that put `confirm` on a quantity witness would otherwise be a
    rule that silently never runs."""
    with pytest.raises(ValidationError, match="belong to a sold_by witness"):
        UnitWitness(field="spec_size", shape="quantity", phrases=["يباع بال"])
    with pytest.raises(ValidationError, match="belong to a sold_by witness"):
        UnitWitness(field="spec_size", confirm=_CONFIRM)
