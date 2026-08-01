"""0057: the weight a price is quoted against, and the unit nobody may invent.

0056 stored the site's quantity NUMBERS — is_qty_decimal, a 0.25 minimum, a
0.05 step — and left the weight those are quantities OF on the floor, so the
row still could not say what 4,830 was FOR. This is the other half.

TWO TESTS CARRY THE WHOLE ARGUMENT and the rest support them:

  * a unit name the source never published must never reach the data, on ANY
    surface — not the warehouse, not the table, not the file that leaves the
    building;
  * and the rebar member must nevertheless read against the weight the shop
    DID publish, because "say nothing" and "say 4,830 with no referent" are
    not the same answer.

Every value below was read off the live madar store read-only on 2026-07-30 —
the prices, the weights, the 0.25/0.05 rules, storeConfig's "kgs", and the
mesh's thirteen per-child weights. The physical masses are computed from the
site's own stated dimensions and the density of steel.
"""
from __future__ import annotations

import re
from pathlib import Path

from scrapex import db as dbmod
from scrapex import reports
from scrapex.config import ExtractSpec, SourceEntry
from scrapex.connectors.magento import MagentoGraphqlConnector
from scrapex.ingest import ingest_payloads
from scrapex.payload import new_payload
from scrapex.reports import price_basis
from scrapex.rowspec import PRODUCT_PRICES, RowView
from scrapex.vocab import ExtractKind, ExtractScope

# --- the store, as it publishes itself ---------------------------------------
#
# GroupedProduct 10115-HSS. Both members declare weight 1000 — every one of the
# live 96 does, whatever the diameter — with is_qty_decimal, a 0.25 minimum and
# a 0.05 step.
#
# THE ARITHMETIC, and it is the reason this file exists. A 12 m Ø8 bar is
# 4.735 kg of steel and a 12 m Ø32 bar is 75.76 kg. Per PIECE the two prices
# would be 1,020 and 53 riyals a kilogram, on the same shelf. Against the
# stated 1000 they are 4.83 and 4.05 — thin dearer than thick, exactly as
# rolling mills price rebar.
_REBAR = {
    "__typename": "GroupedProduct",
    "uid": "SFNT", "sku": "10115-HSS", "url_key": "hadeed-epoxy-coated-steel-rebar",
    "name": " حديد تسليح ابوكسي من حديد", "stock_status": "IN_STOCK", "categories": [],
    "price_range": {"minimum_price": {"regular_price": {"value": 4045.13},
                                      "final_price": {"value": 4045.13}},
                    "maximum_price": {"final_price": {"value": 4045.13}}},
    "items": [
        {"qty": 0, "position": 1, "product": {
            "uid": "TjY1", "sku": "101150812",
            "name": "حديد أبوكسي من حديد | 8مم × 12متر | ASTM A775 جريد 60",
            "stock_status": "IN_STOCK", "weight": 1000,
            "is_qty_decimal": True, "min_sale_qty": 0.25, "qty_increments": 0.05,
            "only_x_left_in_stock": None,
            "price_range": {"minimum_price": {"regular_price": {"value": 4830.0},
                                              "final_price": {"value": 4830.0}}}}},
        {"qty": 0, "position": 2, "product": {
            "uid": "Tjcy", "sku": "101153212",
            "name": "حديد أبوكسي من حديد | 32مم × 12متر | ASTM A775 جريد 60",
            "stock_status": "IN_STOCK", "weight": 1000,
            "is_qty_decimal": True, "min_sale_qty": 0.25, "qty_increments": 0.05,
            "only_x_left_in_stock": 8,
            "price_range": {"minimum_price": {"regular_price": {"value": 4045.13},
                                              "final_price": {"value": 4045.13}}}}},
    ],
}

# "Sold by a bulk unit" is NOT a Magento shape — it appears inside
# ConfigurableProduct too. The steel mesh's children carry per-child weights
# (6.74 .. 66.02 kg live), which is why the weight rides the OFFER and one
# figure per family would be wrong twelve times out of thirteen.
_MESH = {
    "__typename": "ConfigurableProduct",
    "uid": "U1JN", "sku": "10400-SRM", "url_key": "steel-reinforcing-mesh",
    "name": "شبك حديد صبة", "stock_status": "IN_STOCK", "categories": [],
    "price_range": {"minimum_price": {"regular_price": {"value": 30.19},
                                      "final_price": {"value": 30.19}},
                    "maximum_price": {"final_price": {"value": 229.43}}},
    "configurable_options": [{"attribute_code": "mesh_size", "label": "المقاس"}],
    "variants": [
        {"attributes": [{"code": "mesh_size", "label": "4.00ملم * 1.5 * 4.0متر"}],
         "product": {
            "uid": "U1JNNA==", "sku": "10404154020",
            "name": "شبك حديد صبة - 4.00ملم * 1.5 * 4.0متر - 20*20سم",
            "stock_status": "IN_STOCK", "weight": 6.74,
            "is_qty_decimal": True, "min_sale_qty": 1, "qty_increments": 1,
            "only_x_left_in_stock": None,
            "price_range": {"minimum_price": {"regular_price": {"value": 30.19},
                                              "final_price": {"value": 30.19}}}}},
        # TWO SIZES THE SHOP HAPPENS TO PRICE THE SAME, and they are live:
        # 10408150420 weighs 25.86 kg and 104075154020 weighs 22.73 kg, and on
        # 2026-07-30 both cost 84.00. They fold together on the Data page,
        # which is the one way a wrong basis could reach a reader — see the
        # test at the end of this file.
        {"attributes": [{"code": "mesh_size", "label": "8.00ملم * 1.5 * 4.0متر"}],
         "product": {
            "uid": "U1JNOA==", "sku": "10408150420",
            "name": "شبك حديد صبة - 8.00ملم * 1.5 * 4.0متر - 20*20سم",
            "stock_status": "IN_STOCK", "weight": 25.86,
            "is_qty_decimal": True, "min_sale_qty": 1, "qty_increments": 1,
            "only_x_left_in_stock": None,
            "price_range": {"minimum_price": {"regular_price": {"value": 96.6},
                                              "final_price": {"value": 96.6}}}}},
        {"attributes": [{"code": "mesh_size", "label": "7.50ملم * 1.5 * 4.0متر"}],
         "product": {
            "uid": "U1JNNzU=", "sku": "104075154020",
            "name": "شبك حديد صبة - 7.50ملم * 1.5 * 4.0متر - 20*20سم",
            "stock_status": "IN_STOCK", "weight": 22.73,
            "is_qty_decimal": True, "min_sale_qty": 1, "qty_increments": 1,
            "only_x_left_in_stock": None,
            "price_range": {"minimum_price": {"regular_price": {"value": 96.6},
                                              "final_price": {"value": 96.6}}}}},
    ],
}

# The source stating its basis IN WORDS: weight 50 AND «50كجم» in the name.
# That agreement is what selling_unit_from trusts, so this row reaches the Unit
# column through the ordinary path and must never reach price_basis.
_CEMENT = {
    "__typename": "ConfigurableProduct",
    "uid": "UkNG", "sku": "70501-RCF", "url_key": "riyadh-cement",
    "name": "اسمنت الرياض", "stock_status": "IN_STOCK", "categories": [],
    "price_range": {"minimum_price": {"regular_price": {"value": 15.23},
                                      "final_price": {"value": 15.23}},
                    "maximum_price": {"final_price": {"value": 27.83}}},
    "configurable_options": [{"attribute_code": "cement_type", "label": "نوع الاسمنت"}],
    "variants": [
        {"attributes": [{"code": "cement_type", "label": "اسمنت ابيض"}],
         "product": {
            "uid": "QzE1OTI=", "sku": "70502001",
            "name": "اسمنت ابيض - 50كجم - اسمنت الرياض",
            "stock_status": "IN_STOCK", "weight": 50,
            "is_qty_decimal": False, "min_sale_qty": 450, "qty_increments": 450,
            "only_x_left_in_stock": None,
            "price_range": {"minimum_price": {"regular_price": {"value": 27.83},
                                              "final_price": {"value": 27.83}}}}},
    ],
}

# THE CONTROL, and the reason the decimal flag is load-bearing. A steel angle
# publishes a weight like everything else on this store — all 3,418 live leaves
# do — and 4.986 kg is the mass of one PIECE. Its price is per piece. If a
# published weight alone were enough to render a basis, this row would read
# "per 4.986 kg" and the fix would have become the bug.
_ANGLE = {
    "__typename": "SimpleProduct",
    "uid": "QU5HTEU=", "sku": "10201002", "url_key": "steel-angle",
    "name": "زاوية حديد 20*20*3 ملم", "stock_status": "IN_STOCK", "categories": [],
    "weight": 4.986, "is_qty_decimal": False, "min_sale_qty": 1, "qty_increments": 1,
    "only_x_left_in_stock": None,
    "price_range": {"minimum_price": {"regular_price": {"value": 32.2},
                                      "final_price": {"value": 32.2}},
                    "maximum_price": {"final_price": {"value": 32.2}}},
}

_CENSUS = {"data": {"products": {
    "page_info": {"current_page": 1, "total_pages": 1},
    "items": [_REBAR, _MESH, _CEMENT, _ANGLE]}}}

_ENGLISH = {"data": {"products": {
    "page_info": {"current_page": 1, "total_pages": 1},
    "items": [
        {"uid": "SFNT", "name": "Hadeed Epoxy Coated Steel Rebar", "items": [
            {"product": {"uid": "TjY1",
                         "name": "Hadeed Epoxy Rebar| Ø8mm × 12m | ASTM A775 Grade 60"}},
            {"product": {"uid": "Tjcy",
                         "name": "Hadeed Epoxy Rebar| Ø32mm × 12m | ASTM A775 Grade 60"}},
        ]},
        {"uid": "U1JN", "name": "Steel Reinforcing Mesh"},
        {"uid": "UkNG", "name": "Riyadh Cement"},
        {"uid": "QU5HTEU=", "name": "Steel Angle 20*20*3 mm"},
    ]}}}


class _Response:
    def __init__(self, payload): self._payload = payload
    def json(self): return self._payload


class _Fetcher:
    """The live store's answers. `weight_unit` is what storeConfig really
    returns — "kgs" on ar_SA and en_SA alike, read 2026-07-30."""

    def __init__(self, weight_unit: str | None = "kgs"):
        self.weight_unit = weight_unit
        self.store_config_requests = 0

    def post(self, url, json=None, **kwargs):
        query = (json or {}).get("query", "")
        page = (json or {}).get("variables", {}).get("currentPage", 1)
        if "storeConfig" in query:
            self.store_config_requests += 1
            if self.weight_unit is None:      # a store that will not say
                return _Response({"data": {"storeConfig": {}}})
            return _Response({"data": {"storeConfig": {"weight_unit": self.weight_unit}}})
        if (kwargs.get("headers") or {}).get("Store"):
            if "categoryList" in query:
                return _Response({"data": {"categoryList": [{"children": []}]}})
            return _Response(_ENGLISH if page == 1 else
                             {"data": {"products": {"items": []}}})
        if "categoryList" in query:
            return _Response({"data": {"categoryList": [{"children": []}]}})
        if "category_uid" in query:
            return _Response({"data": {"products": {
                "items": [], "page_info": {"current_page": 1, "total_pages": 1}}}})
        return _Response(_CENSUS if page == 1 else
                         {"data": {"products": {"items": []}}})

    def close(self): pass


def _entry() -> SourceEntry:
    return SourceEntry.model_validate(dict(
        source_key="MADAR", source_name="المدار", base_url="https://www.madar.com",
        family="magento-graphql", currency="SAR", default_region="SA", vat_mode="incl",
        extract=[ExtractSpec(kind=ExtractKind.PRODUCT_PRICES, scope=ExtractScope.CENSUS)],
    ))


def _tables(fetcher: _Fetcher | None = None):
    return [t for t in MagentoGraphqlConnector(fetcher or _Fetcher()).fetch(_entry())
            if t.kind == ExtractKind.PRODUCT_PRICES]


def _rows(fetcher: _Fetcher | None = None) -> list[dict]:
    tables = _tables(fetcher)
    view = RowView(PRODUCT_PRICES, tables[0].header)
    return [view.as_dict(row) for table in tables for row in table.rows]


def _by_sku(sku: str, fetcher: _Fetcher | None = None) -> dict:
    found = [r for r in _rows(fetcher) if r["external_sku"] == sku]
    assert len(found) == 1, f"expected exactly one row for {sku}, got {len(found)}"
    return found[0]


def _ingest(tmp_path: Path, fetcher: _Fetcher | None = None):
    conn = dbmod.connect(tmp_path / "harvest.db")
    dbmod.migrate(conn)
    tables = _tables(fetcher)
    # new_payload, not FunnelPayload directly: it is the only blessed producer
    # and it stamps BOTH numbers, so these rows travel exactly as a real crawl's
    # do — content 8 declaring generation 5. That declaration is the entire
    # reason the Apps Script already pasted in the owner's sheet can read them.
    ingest_payloads(conn, _entry(), [new_payload(
        source_key="MADAR", kind=ExtractKind.PRODUCT_PRICES, client="cli",
        scraped_at="2026-07-30T10:00:00Z", source_url=t.source_url,
        header=t.header, rows=t.rows) for t in tables])
    return conn


def _row_for(conn, sku: str) -> dict:
    rows = [r for r in reports.table_payload(conn, "MADAR")["rows"]
            if r.get("sku") == sku]
    assert len(rows) == 1, f"expected one table row for {sku}, got {len(rows)}"
    return rows[0]


# =============================================================================
# THE FIRST OF THE TWO. A unit the source never published must not reach the
# data — on any surface, by any route.
# =============================================================================

# The words madar has never DECLARED as a unit. Re-verified read-only
# 2026-07-30: its GraphQL schema has no `unit`, `uom` or `measure` field at
# all, and not one of the rebar member's 22 custom_attributesV2 names the unit
# its price is quoted in. So "the unit is a tonne" is OUR inference, and an
# inference has no business in a column that means "the source said this".
#
# It says «طن» in its MARKETING PROSE, which is a different thing and is
# asserted separately below — see the pair of tests at the end of this file.
_NEVER_PUBLISHED = ("tonne", "tonnes", "ton", "tons", "metric ton", "t", "طن")

# «طن» as a WORD, not as the tail of «قطن» (cotton) or «بطن». A substring test
# would fail on real Arabic product names and teach everyone to ignore it.
_STANDALONE_TON = re.compile(
    r"(?<![؀-ۿ])طن(?![؀-ۿ])|\btonnes?\b|\bmetric\s+tons?\b",
    re.IGNORECASE)


# EVERY COLUMN IN THE WAREHOUSE THAT MEANS "A UNIT". These are the only places
# an invented unit could land, and between them they are exhaustive: a unit
# reaches a reader either as a selling_unit row, as an offer's weight unit, or
# as text a display layer composed from one of those two.
#
# The sweep is deliberately NOT "the word appears nowhere in the database".
# That invariant is FALSE and a test asserting it would be a trap: madar's own
# marketing prose says «أفضل سعر طن حديد في السعودية» in the meta_title of 7 of
# the 19 products behind these offers, and «قطنية» (cotton) contains the letters
# outright. Source prose is the source's, and deleting it to make a test pass
# would be the very edit this file exists to forbid. What must stay clean is
# the set of columns where WE do the writing.
_UNIT_BEARING_COLUMNS = (
    ("selling_unit", "unit_code"),
    ("source_offer", "weight_unit"),
)


def _stored_units(conn):
    """(table.column, value) for every cell in the warehouse that means a unit."""
    for table, column in _UNIT_BEARING_COLUMNS:
        for (value,) in conn.execute(
                f'SELECT DISTINCT "{column}" FROM "{table}" '
                f'WHERE COALESCE("{column}", \'\') <> \'\''):
            yield f"{table}.{column}", value


def test_no_unit_the_source_never_published_reaches_the_data(tmp_path):
    """THE GUARD. Fail if anything, anywhere, calls this a tonne.

    Three routes, because a word can arrive by any of them: as a UNIT the
    warehouse minted, as TEXT written into some other column, or rendered onto
    a screen or into a file by a display layer that decided to be helpful.
    """
    conn = _ingest(tmp_path)

    # 1. THE UNIT VOCABULARY. selling_unit is resolve-or-create — units arrive
    #    from sites, so nothing seeds it and nothing constrains it. A connector
    #    that inferred a bulk unit would mint the row here.
    minted = {code for (code,) in conn.execute("SELECT unit_code FROM selling_unit")}
    assert not (minted & set(_NEVER_PUBLISHED)), (
        f"a unit the shop never printed was minted: {minted & set(_NEVER_PUBLISHED)}")

    # 2. THE OFFER ITSELF. The rebar's two offers must hold no selling unit at
    #    all — empty is the honest answer to "what unit did the shop state?".
    units = conn.execute(
        "SELECT sv.external_sku, so.selling_unit_id, so.basis_quantity "
        "FROM source_offer so "
        "JOIN source_variant sv ON sv.source_variant_id = so.source_variant_id "
        "WHERE sv.external_sku IN ('101150812','101153212')").fetchall()
    assert len(units) == 2
    for sku, unit_id, basis in units:
        assert unit_id is None, f"{sku} was given a selling unit nobody published"
        # ...and basis_quantity is untouched at its schema default. Writing
        # 1000 here would both assert "per 1000 <unit>" and change the offer's
        # identity, minting a second offer beside the first.
        assert basis == 1, f"{sku} had its basis_quantity rewritten to {basis}"

    # 3. EVERY UNIT-BEARING COLUMN IN THE WAREHOUSE, whatever the source. Not
    #    only this crawl's offers: a unit is a shared vocabulary, and one
    #    connector inventing a bulk unit poisons it for every source that
    #    joins the same table.
    offenders = [(where, value) for where, value in _stored_units(conn)
                 if _STANDALONE_TON.search(value) or value in _NEVER_PUBLISHED]
    assert not offenders, f"a unit nobody published was stored: {offenders}"

    # 4. WHAT THE READER SEES. The Unit column, the price cell's basis, and the
    #    exported file — a display layer is just as capable of inventing a word
    #    as a connector is, and it is the surface the owner actually reads.
    for row in reports.table_payload(conn, "MADAR")["rows"]:
        for key in ("unit", "price_basis"):
            assert not _STANDALONE_TON.search(str(row.get(key) or "")), (
                f"the table rendered {row.get(key)!r} in {key}")
    header, table = reports.export_source_table(conn, "MADAR")[:2]
    for line in table:
        for cell in line:
            assert not _STANDALONE_TON.search(str(cell or "")), (
                f"the export rendered {cell!r}")


def test_the_connector_emits_no_unit_for_a_product_whose_unit_the_shop_never_states():
    """Upstream of the warehouse, at the only place that could invent one.

    The connector HAS the weight and HAS the decimal flag, so it is exactly
    where "obviously that means tonnes" would get written down. It records the
    numbers and stops.
    """
    thin = _by_sku("101150812")
    assert thin["unit"] == "" and thin["basis_quantity"] == ""
    assert thin["weight"] == "1000" and thin["weight_unit"] == "kgs"
    assert thin["quantity_is_decimal"] == "1"
    assert thin["minimum_quantity"] == "0.25" and thin["quantity_increment"] == "0.05"


# =============================================================================
# THE SECOND OF THE TWO. The member renders against the weight the shop DID
# publish — and the price itself is not touched.
# =============================================================================

def test_the_rebar_member_renders_against_its_published_weight(tmp_path):
    """4,830 stays 4,830. Only what surrounds it changes.

    Ø8 at 4,830 and Ø32 at 4,045 is impossible per bar — 1,020 against 53
    riyals a kilogram of the same steel — and against the 1000 the shop states
    for both it is 4.83 against 4.05, thin dearer than thick. That second
    reading is the one the page now shows, in the shop's own number and the
    shop's own word for its unit.
    """
    conn = _ingest(tmp_path)

    thin = _row_for(conn, "101150812")
    thick = _row_for(conn, "101153212")

    # THE PRICE IS UNTOUCHED. Nothing here divides, multiplies or rounds.
    assert thin["price"] == 4830.0
    assert thick["price"] == 4045.13

    # THE UNIT COLUMN STAYS EMPTY, because the shop stated no unit.
    assert thin["unit"] == "" and thick["unit"] == ""

    # ...and the price cell says what one unit of that price buys.
    assert thin["price_basis"] == "1,000 kg"
    assert thick["price_basis"] == "1,000 kg"

    # The warehouse holds the two facts it was told, and only those.
    stored = conn.execute(
        "SELECT so.weight, so.weight_unit, so.quantity_is_decimal "
        "FROM source_offer so "
        "JOIN source_variant sv ON sv.source_variant_id = so.source_variant_id "
        "WHERE sv.external_sku = '101150812'").fetchone()
    assert tuple(stored) == (1000.0, "kg", 1)


def test_the_exported_file_carries_the_basis_beside_the_empty_unit(tmp_path):
    """The screen and the spreadsheet have to agree. A file of bare numbers
    where 4,830 is per 1,000 kg and 32.20 is per piece is the trap the Unit
    column exists to prevent, and the export is the record leaving the
    building."""
    conn = _ingest(tmp_path)
    header, table = reports.export_source_table(conn, "MADAR")[:2]
    unit_at = header.index("unit")
    basis_at = header.index("price_basis")
    sku_at = header.index("sku")
    by_sku = {line[sku_at]: line for line in table}

    assert by_sku["101150812"][unit_at] == ""
    assert by_sku["101150812"][basis_at] == "1,000 kg"
    # The cement states its unit in words, so it answers in the Unit column and
    # leaves this one empty. The two never both fill.
    assert by_sku["70502001"][unit_at] == "50 kg"
    assert by_sku["70502001"][basis_at] == ""


def test_a_published_weight_alone_is_not_a_basis(tmp_path):
    """THE CONTROL, and the reason the decimal flag is load-bearing.

    All 3,418 live madar leaves publish a weight (measured 2026-07-30), and for
    3,309 of them it is the mass of one PIECE. Rendering on weight alone would
    print "per 4.986 kg" against a steel angle sold by the piece — precisely
    the guess normalize.selling_unit_from was written to refuse, applied to the
    whole shop.
    """
    conn = _ingest(tmp_path)
    angle = _row_for(conn, "10201002")
    assert angle["price"] == 32.2
    assert angle["unit"] == "" and angle["price_basis"] == ""
    # The weight is still STORED — it is a fact the shop published, and the
    # rule decides where it is shown, not whether it is kept.
    assert tuple(conn.execute(
        "SELECT so.weight, so.weight_unit FROM source_offer so "
        "JOIN source_variant sv ON sv.source_variant_id = so.source_variant_id "
        "WHERE sv.external_sku = '10201002'").fetchone()) == (4.986, "kg")


def test_a_stated_unit_always_wins_over_a_published_weight(tmp_path):
    """Riyadh cement says «50كجم» in the name AND weight 50, and that agreement
    is what makes the basis trustworthy. It reaches the Unit column through the
    path that already existed and must never be re-answered from the weight."""
    conn = _ingest(tmp_path)
    cement = _row_for(conn, "70502001")
    assert cement["unit"] == "50 kg"
    assert cement["price_basis"] == ""


def test_the_mechanism_is_not_a_madar_special_case(tmp_path):
    """The rule is "a source publishing a decimal quantity against a weight",
    not "the rebar". It fires inside a ConfigurableProduct too — the steel mesh
    — which is why the weight rides the OFFER and not the product: its live
    children span 6.74 .. 66.02 kg, so one figure for the family would be wrong
    twelve times out of thirteen."""
    conn = _ingest(tmp_path)
    mesh = _row_for(conn, "10404154020")
    assert mesh["price"] == 30.19
    assert mesh["unit"] == ""
    assert mesh["price_basis"] == "6.74 kg"


# ---- price_basis itself, condition by condition ------------------------------

def test_price_basis_needs_all_three_of_the_sources_own_statements():
    # Everything present: the shop's weight, the shop's unit, the shop's flag.
    assert price_basis("", 1000, "kg", 1) == "1,000 kg"
    # A stated selling unit is the answer; the weight is then a piece's mass.
    assert price_basis("kg", 1000, "kg", 1) == ""
    # The shop does not say the quantity is divisible.
    assert price_basis("", 1000, "kg", 0) == ""
    # The shop publishes no weight.
    assert price_basis("", None, "kg", 1) == ""
    # The shop publishes a weight and will not say what unit it is in. This is
    # the storeConfig-failed case, and a number with a unit we assumed is worse
    # than no number at all.
    assert price_basis("", 1000, "", 1) == ""
    # Weightlessness is not a fact any shop states.
    assert price_basis("", 0, "kg", 1) == ""


def test_the_basis_is_grouped_and_keeps_the_sources_own_precision():
    """1,000 not 1000 — the whole point is that the number is large. And the
    reader's own units: the shop said 1000 kg, so it says 1,000 kg, never 1 t.
    A tonne is a word this shop has not used."""
    assert price_basis("", 1000, "kg", 1) == "1,000 kg"
    assert price_basis("", 66.02, "kg", 1) == "66.02 kg"
    assert price_basis("", 6.74, "kg", 1) == "6.74 kg"
    # A store weighing in pounds renders pounds, with nothing here changing.
    assert price_basis("", 2204.62, "lb", 1) == "2,204.62 lb"


def test_a_store_that_will_not_state_its_weight_unit_shows_no_basis(tmp_path):
    """The refusal, end to end. storeConfig is one request per crawl and it can
    fail; when it does, the basis disappears and the price cell reads exactly
    as it did before this change. The run SAYS SO rather than falling back on
    "everyone means kilograms"."""
    silent = _Fetcher(weight_unit=None)
    conn = _ingest(tmp_path, silent)
    assert silent.store_config_requests == 1     # once per crawl, not per row

    thin = _row_for(conn, "101150812")
    assert thin["price"] == 4830.0               # the price is never affected
    assert thin["unit"] == "" and thin["price_basis"] == ""
    # Neither half is stored, because half of this fact is not a fact.
    assert tuple(conn.execute(
        "SELECT so.weight, so.weight_unit FROM source_offer so "
        "JOIN source_variant sv ON sv.source_variant_id = so.source_variant_id "
        "WHERE sv.external_sku = '101150812'").fetchone()) == (None, None)
    # And the crawl reports it, so a silently basis-less table has a reason
    # a reader can find.
    warnings = [w for t in _tables(_Fetcher(weight_unit=None)) for w in t.warnings]
    assert any("weight_unit" in w for w in warnings), warnings


# ---- migration 0057 ----------------------------------------------------------

def test_migration_0057_adds_the_two_columns_without_touching_offer_identity():
    """Both columns are outside ux_source_offer_identity, so an existing offer
    LEARNS them instead of a second offer being minted beside it — the
    duplicate-row defect that appeared the day the sika connector learned to
    read "5 KG" off a name and 56 products grew a twin."""
    conn = dbmod.connect(":memory:")
    try:
        for number, file in dbmod._migration_files():        # the pre-0057 warehouse
            if number >= 57:
                continue
            conn.executescript(file.read_text(encoding="utf-8"))
            conn.execute(f"PRAGMA user_version = {number}")
        columns = {r[1] for r in conn.execute("PRAGMA table_info(source_offer)")}
        assert "weight" not in columns and "weight_unit" not in columns

        assert dbmod.migrate(conn) == [57]

        columns = {r[1]: r for r in conn.execute("PRAGMA table_info(source_offer)")}
        assert "weight" in columns and "weight_unit" in columns
        # Nullable and undefaulted: NULL reads as "the site did not say", which
        # is the truthful state of every row that predates the next crawl. A 0
        # would be a source claiming weightlessness.
        assert columns["weight"][3] == 0 and columns["weight"][4] is None
        assert columns["weight_unit"][3] == 0 and columns["weight_unit"][4] is None

        indexed = {r[2] for r in conn.execute(
            "PRAGMA index_info(ux_source_offer_identity)")}
        assert "weight" not in indexed and "weight_unit" not in indexed
    finally:
        conn.close()


# ---- the other side of the same rule ----------------------------------------

def test_the_shops_own_word_for_a_tonne_survives_verbatim(tmp_path):
    """SOURCE TRUTH IS NEVER EDITED — including when the source says the very
    thing we refused to say for it.

    Measured on the live crawl of 2026-07-30: madar's own marketing prose DOES
    print «طن». Seven of the nineteen products behind these 109 offers carry it
    in a meta field — the epoxy rebar's meta_title reads «أفضل سعر طن حديد في
    السعودية» ("the best price per tonne of steel in Saudi Arabia") — and the
    Rajhi rebar's says «سعر طن حديد التسليح اليوم».

    Two things follow, and they pull in opposite directions, which is exactly
    why this test sits beside the guard above:

      * That prose is the SHOP's and is kept exactly as written. A sweep that
        banned the word from the whole warehouse would have to delete it, which
        is the edit this file exists to forbid — and would also trip over
        «قطنية» (cotton), where the letters are a substring of another word.
      * It is still NOT a unit declaration. It is an SEO keyword on a category
        page, it says nothing about which figure on which SKU it qualifies, and
        twelve of the same nineteen products say nothing at all. Promoting it
        into `unit` would make the same 109 offers disagree with each other
        about a fact none of them states.

    So the word lives in the attribute the shop wrote it in, and the unit
    columns stay empty. Both halves are asserted here.
    """
    conn = _ingest(tmp_path)
    product_id = conn.execute(
        "SELECT sv.source_product_id FROM source_variant sv "
        "WHERE sv.external_sku = '101150812'").fetchone()[0]
    # The shop's real wording, copied from the live store 2026-07-30.
    published = "حديد تسليح (حديد) - سابك سابقاً | أفضل سعر طن حديد في السعودية"
    conn.execute(
        "INSERT INTO source_product_attribute "
        "(source_product_id, attribute_code, attribute_label, raw_value, lang) "
        "VALUES (?, 'meta_title_ar', 'Meta title', ?, 'ar')",
        (product_id, published))
    conn.commit()

    kept = conn.execute(
        "SELECT raw_value FROM source_product_attribute "
        "WHERE source_product_id = ? AND attribute_code = 'meta_title_ar'",
        (product_id,)).fetchone()[0]
    assert kept == published, "the shop's own sentence was altered"
    assert _STANDALONE_TON.search(kept), "the fixture no longer exercises the case"

    # ...and not one unit column learned the word from it.
    assert not [v for _where, v in _stored_units(conn) if _STANDALONE_TON.search(v)]
    thin = _row_for(conn, "101150812")
    assert thin["unit"] == ""
    assert thin["price_basis"] == "1,000 kg"


def test_the_word_boundary_is_real_and_not_a_substring_match():
    """«قطنية» (cotton) contains the letters of «طن» and is a real madar
    product — "قفازات عمل قطنية" (cotton work gloves), live 2026-07-30. A
    substring test would fire on it, get muted, and stop guarding anything."""
    assert not _STANDALONE_TON.search("قفازات عمل قطنية مطلية باللاتكس")
    assert not _STANDALONE_TON.search("بطن")
    assert _STANDALONE_TON.search("أفضل سعر طن حديد في السعودية")
    assert _STANDALONE_TON.search("1 طن، 2 طن، 3 طن")
    assert _STANDALONE_TON.search("priced per tonne")
    assert not _STANDALONE_TON.search("carton of buttons")


def test_folding_two_variants_priced_alike_never_lends_one_its_neighbours_weight(tmp_path):
    """The one way a WRONG basis could reach a reader, and it is already shut.

    fold_variant_rows groups by (product, price, currency, country) so a shop's
    six colours at one price read as one row. Two mesh sizes can collide there:
    live on 2026-07-30, 10408150420 (25.86 kg) and 104075154020 (22.73 kg) both
    cost 84.00 after tax is taken off. Folded, the row must not show either
    weight — one member's 25.86 standing for a group that also contains 22.73
    is a number that is wrong for half the thing it describes.

    Nothing new was written for this. The fold's standing rule — a field the
    members disagree about goes BLANK rather than taking the first row's answer
    — already covers any column, which is why the basis was given a column of
    its own instead of being composed at the last moment in the browser.
    """
    conn = _ingest(tmp_path)

    apart = reports.table_payload(conn, "MADAR")["rows"]
    by_sku = {r["sku"]: r for r in apart}
    # Told apart, each says its own weight...
    assert by_sku["10408150420"]["price_basis"] == "25.86 kg"
    assert by_sku["104075154020"]["price_basis"] == "22.73 kg"
    assert by_sku["10408150420"]["price"] == by_sku["104075154020"]["price"]

    # ...and folded together, the row says nothing rather than something false.
    folded = [r for r in reports.table_payload(conn, "MADAR", fold_variants=True)["rows"]
              if r.get("variants", 1) > 1 and "10408150420" in str(r.get("sku"))]
    assert len(folded) == 1, folded
    assert folded[0]["variants"] == 2
    assert folded[0]["price_basis"] == ""

    # The mesh child that does NOT collide keeps its own basis when folding is on.
    alone = [r for r in reports.table_payload(conn, "MADAR", fold_variants=True)["rows"]
             if r.get("sku") == "10404154020"]
    assert alone and alone[0]["price_basis"] == "6.74 kg"
