"""0056: HOW THE SITE SHOWS IT, and WHAT ONE UNIT OF THE PRICE BUYS.

Two facts that were being conflated, and every value below was read off the
LIVE madar store on 2026-07-29 rather than invented — the rebar prices, the
weights, the 0.25/0.05 quantity rules, the cement 450-bag minimum, the English
member names and the shape census counts.

The centrepiece is the arithmetic that proves the defect without needing the
site's word for it: the Ø8mm member costs MORE than the Ø32mm one. Per piece
that is impossible; per tonne it is exactly right.
"""
from __future__ import annotations

import json
from pathlib import Path

from scrapex import db as dbmod
from scrapex.config import ExtractSpec, SourceEntry
from scrapex.connectors.magento import MagentoGraphqlConnector
from scrapex.ingest import ingest_payloads
from scrapex.payload import PAYLOAD_VERSION, FunnelPayload
from scrapex.rowspec import PRODUCT_PRICES, RowView
from scrapex.vocab import DisplayMethod, ExtractKind, ExtractScope

# --- the four shapes, as the live store publishes them ------------------------
#
# GroupedProduct 10115-HSS — «حديد تسليح ابوكسي من حديد». Every member declares
# weight 1000, is_qty_decimal true, a 0.25 minimum in 0.05 steps. The two
# members kept here are the ones whose prices carry the whole argument.
_REBAR = {
    "__typename": "GroupedProduct",
    "uid": "SFNT", "sku": "10115-HSS", "url_key": "hadeed-epoxy-coated-steel-rebar",
    "name": " حديد تسليح ابوكسي من حديد", "stock_status": "IN_STOCK",
    "categories": [],
    # Magento answers max == min on every one of the 33 grouped products even
    # when the members really span 55% — which is why the grouped branch never
    # reads this and _display_method takes the typename alone.
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

# ConfigurableProduct 70501-RCF — «اسمنت الرياض». The children are priced apart
# (15.23 .. 27.83), so the page shows "from X". min_sale_qty 450 in steps of
# 450 at 50 kg a bag: the price is only obtainable at 22.5 tonnes per order.
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

# A configurable whose options are all one price — the page shows a single
# figure, not a "from".
_SOCKETS = {
    "__typename": "ConfigurableProduct",
    "uid": "TEVH", "sku": "60402-LPF", "url_key": "legrand-sockets",
    "name": "علب أرضية منبثقة من ليجراند", "stock_status": "IN_STOCK", "categories": [],
    "price_range": {"minimum_price": {"regular_price": {"value": 194.9},
                                      "final_price": {"value": 194.9}},
                    "maximum_price": {"final_price": {"value": 194.9}}},
    "configurable_options": [{"attribute_code": "gangs", "label": "عدد الوحدات"}],
    "variants": [
        {"attributes": [{"code": "gangs", "label": "3"}],
         "product": {
            "uid": "TEVHMw==", "sku": "054010",
            "name": "054010 FLOOR BACK BOX POPUP ALU 3MOD LEGRAND",
            "stock_status": "IN_STOCK", "weight": 1.4,
            "is_qty_decimal": False, "min_sale_qty": 1, "qty_increments": 1,
            "only_x_left_in_stock": None,
            "price_range": {"minimum_price": {"regular_price": {"value": 194.9},
                                              "final_price": {"value": 194.9}}}}},
    ],
}

# A plain SimpleProduct: one product, one price, and the shop's own count.
_PUTTY = {
    "__typename": "SimpleProduct",
    "uid": "UFVUVFk=", "sku": "71205003", "url_key": "putty-1-kg-sab",
    "name": " معجون سابك 1 كجم", "stock_status": "IN_STOCK", "categories": [],
    "weight": 1, "is_qty_decimal": False, "min_sale_qty": 1, "qty_increments": 1,
    "only_x_left_in_stock": 8,
    "price_range": {"minimum_price": {"regular_price": {"value": 65.21},
                                      "final_price": {"value": 65.21}},
                    "maximum_price": {"final_price": {"value": 65.21}}},
}

_CENSUS = {"data": {"products": {
    "page_info": {"current_page": 1, "total_pages": 1},
    "items": [_REBAR, _CEMENT, _SOCKETS, _PUTTY]}}}

# The en_SA store view. It publishes an English name for every grouped MEMBER —
# 161 of 161 live, 150 of them genuinely different from the Arabic — and this
# is the half that never arrived, because both English queries carried a
# ConfigurableProduct fragment and no GroupedProduct one.
_ENGLISH = {"data": {"products": {
    "page_info": {"current_page": 1, "total_pages": 1},
    "items": [
        {"uid": "SFNT", "name": "Hadeed Epoxy Coated Steel Rebar", "items": [
            {"product": {"uid": "TjY1",
                         "name": "Hadeed Epoxy Rebar| Ø8mm × 12m | ASTM A775 Grade 60"}},
            {"product": {"uid": "Tjcy",
                         "name": "Hadeed Epoxy Rebar| Ø32mm × 12m | ASTM A775 Grade 60"}},
        ]},
        {"uid": "UkNG", "name": "Riyadh Cement",
         "configurable_options": [{"attribute_code": "cement_type", "label": "Cement Type"}],
         "variants": [{"attributes": [{"code": "cement_type", "label": "White Cement"}],
                       "product": {"uid": "QzE1OTI=", "name": "White Cement - 50kg"}}]},
        {"uid": "TEVH", "name": "Legrand Pop-up Floor Box Kit"},
        {"uid": "UFVUVFk=", "name": "SABIC Putty 1 kg"},
    ]}}}


class _Response:
    def __init__(self, payload): self._payload = payload
    def json(self): return self._payload


class _Fetcher:
    def __init__(self): self.requests_count = 0

    def post(self, url, json=None, **kwargs):
        self.requests_count += 1
        query = (json or {}).get("query", "")
        page = (json or {}).get("variables", {}).get("currentPage", 1)
        if (kwargs.get("headers") or {}).get("Store"):
            if "categoryList" in query:
                return _Response({"data": {"categoryList": [{"children": []}]}})
            return _Response(_ENGLISH if page == 1 else
                             {"data": {"products": {"items": []}}})
        if "storeConfig" in query:
            # The store's own word for the unit of its weights (0057). Read
            # live 2026-07-30: madar answers "kgs" on both store views.
            return _Response({"data": {"storeConfig": {"weight_unit": "kgs"}}})
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


def _rows() -> list[dict]:
    tables = list(MagentoGraphqlConnector(_Fetcher()).fetch(_entry()))
    prices = [t for t in tables if t.kind == ExtractKind.PRODUCT_PRICES]
    view = RowView(PRODUCT_PRICES, prices[0].header)
    return [view.as_dict(row) for table in prices for row in table.rows]


def _by_sku(sku: str) -> dict:
    found = [r for r in _rows() if r["external_sku"] == sku]
    assert len(found) == 1, f"expected exactly one row for {sku}, got {len(found)}"
    return found[0]


# ---- P1: the arithmetic that proves per-tonne is per-tonne -------------------

def test_the_thin_bar_costs_more_than_the_thick_one_which_is_only_possible_per_tonne():
    """THE READY-MADE ASSERTION. A 12 m Ø32 bar carries ~16x the steel of a Ø8
    bar, so per PIECE the Ø8 cannot cost more. It does — 4,830 against 4,045 —
    and per TONNE that is exactly right, because thin bars cost more per tonne
    to roll. The row must therefore carry enough for a reader to know the
    figure is not the price of one bar."""
    thin, thick = _by_sku("101150812"), _by_sku("101153212")
    assert float(thin["price"]) > float(thick["price"]), (
        "the Ø8 member must cost more than the Ø32 one — this is the live data")
    # ...and the facts that make that legible now ride the row.
    assert thin["quantity_is_decimal"] == "1"
    assert thin["minimum_quantity"] == "0.25"
    assert thin["quantity_increment"] == "0.05"


def test_no_unit_is_invented_where_the_site_states_none():
    """The owner's ruling, «الحقائق الخام فقط». The shop publishes weight 1000
    and never the word «طن» — verified 2026-07-29 across member and parent
    attributes, description, meta, both category descriptions, both store
    views and the full rendered page. So the unit column stays EMPTY and the
    numbers carry the meaning. A connector that starts writing 'tonne' here is
    asserting something the shop has never printed."""
    thin = _by_sku("101150812")
    assert thin["unit"] == "", (
        "madar states no unit for rebar; writing one would invent the shop's word")
    assert thin["basis_quantity"] == ""


def test_a_stated_unit_is_still_read_where_the_site_does_state_it():
    """The refusal above is about SILENCE, not about units. Cement states its
    basis twice — weight 50 and «50كجم» in the child's name — and that
    agreement is exactly what selling_unit_from has always required."""
    bag = _by_sku("70502001")
    assert (bag["unit"], bag["basis_quantity"]) == ("kg", "50")


# ---- P3: the minimum that makes the price obtainable -------------------------

def test_the_cement_minimum_is_captured():
    """450 bags in steps of 450, at 50 kg a bag: the price is only obtainable at
    22.5 tonnes per order. minimum_quantity existed in schema.sql and nothing
    ever read or wrote it."""
    bag = _by_sku("70502001")
    assert bag["minimum_quantity"] == "450"
    assert bag["quantity_increment"] == "450"
    assert bag["quantity_is_decimal"] == "0"


# ---- P4: the stock counts the site publishes --------------------------------

def test_site_published_stock_counts_ride_the_row():
    assert _by_sku("101153212")["stock_quantity"] == "8"
    assert _by_sku("71205003")["stock_quantity"] == "8"
    # ...and a product the site says nothing about stays blank, never 0.
    assert _by_sku("101150812")["stock_quantity"] == ""


# ---- P2: the English variant names the site publishes -----------------------

def test_a_grouped_member_gets_its_english_name():
    """Needed BOTH fixes: the GroupedProduct fragment in _EN_QUERY (so names_en
    learns a member uid at all) and the row() call passing it (so `variant` is
    not built only from axes a member does not have). Either alone leaves the
    column empty, which is how all 162 stored variants came to carry ''."""
    thin = _by_sku("101150812")
    assert thin["variant"] == "Hadeed Epoxy Rebar| Ø8mm × 12m | ASTM A775 Grade 60"
    # The Arabic half is unchanged and still the member's own name.
    assert thin["variant_ar"] == (
        "حديد أبوكسي من حديد | 8مم × 12متر | ASTM A775 جريد 60")


def test_a_configurable_variant_label_is_still_built_from_its_axes():
    """variant_en overrides the axis composition only where there are no axes.
    A configurable child must keep composing «Cement Type: White Cement»."""
    assert _by_sku("70502001")["variant"] == "Cement Type: White Cement"


# ---- the display method, one product of each shape --------------------------

def test_display_method_is_right_for_each_of_the_four_shapes():
    assert _by_sku("101150812")["display_method"] == DisplayMethod.MEMBER_LIST.value
    assert _by_sku("70502001")["display_method"] == DisplayMethod.OPTIONS_PRICED.value
    assert _by_sku("054010")["display_method"] == DisplayMethod.OPTIONS_ONE_PRICE.value
    assert _by_sku("71205003")["display_method"] == DisplayMethod.SINGLE.value


def test_an_unstudied_shape_is_left_blank_rather_than_guessed():
    """A BundleProduct exists nowhere on this store today. When one arrives it
    must file blank — '' means "nobody has studied this", and the column's
    whole value is that it never bluffs."""
    from scrapex.connectors.magento import _display_method
    assert _display_method({"__typename": "BundleProduct"}) == ""
    assert _display_method({}) == ""


def test_display_method_is_constant_across_every_row_a_product_emits():
    """It is a property of the PRODUCT, not of the offer — that is the whole
    reason it sits on source_product and the quantity facts sit on
    source_offer."""
    members = [r for r in _rows() if r["external_product_id"] == "SFNT"]
    assert len(members) == 2
    assert {r["display_method"] for r in members} == {DisplayMethod.MEMBER_LIST.value}


# ---- the simple product is unchanged ----------------------------------------

def test_a_simple_product_is_otherwise_untouched():
    """The regression guard. Everything this commit adds is additive; a simple
    row's existing columns must read exactly as they did before."""
    putty = _by_sku("71205003")
    assert putty["price"] == "65.21"
    assert putty["tax_included"] == "1"          # the storefront figure
    assert putty["external_product_id"] == putty["external_variant_id"]
    assert putty["product_name_ar"] == " معجون سابك 1 كجم"   # the site's own space
    assert putty["product_name"] == "SABIC Putty 1 kg"
    assert putty["variant_ar"] == "" and putty["variant"] == ""
    assert putty["unit"] == "" and putty["basis_quantity"] == ""
    assert putty["parent_sku"] == ""


# ---- P7: the connector states which language it read ------------------------

def test_every_row_states_the_language_it_was_collected_in():
    assert {r["lang"] for r in _rows()} == {"ar"}


# ---- what the warehouse ends up holding -------------------------------------

def _ingest(tmp_path: Path):
    conn = dbmod.connect(tmp_path / "harvest.db")
    dbmod.migrate(conn)
    tables = [t for t in MagentoGraphqlConnector(_Fetcher()).fetch(_entry())
              if t.kind == ExtractKind.PRODUCT_PRICES]
    payloads = [FunnelPayload(
        payload_version=PAYLOAD_VERSION, source_key="MADAR",
        kind=ExtractKind.PRODUCT_PRICES, client="cli",
        scraped_at="2026-07-29T10:00:00Z", source_url=t.source_url,
        header=t.header, rows=t.rows) for t in tables]
    ingest_payloads(conn, _entry(), payloads)
    return conn


def test_the_warehouse_stores_both_facts_in_their_own_places(tmp_path):
    conn = _ingest(tmp_path)
    try:
        shapes = dict(conn.execute(
            "SELECT external_product_id, display_method FROM source_product"))
        assert shapes["SFNT"] == DisplayMethod.MEMBER_LIST.value
        assert shapes["UkNG"] == DisplayMethod.OPTIONS_PRICED.value
        assert shapes["TEVH"] == DisplayMethod.OPTIONS_ONE_PRICE.value
        assert shapes["UFVUVFk="] == DisplayMethod.SINGLE.value

        offer = conn.execute(
            "SELECT o.minimum_quantity, o.quantity_increment, o.quantity_is_decimal "
            "FROM source_offer o JOIN source_variant v USING (source_variant_id) "
            "WHERE v.external_variant_id = 'TjY1'").fetchone()
        assert (offer[0], offer[1], offer[2]) == (0.25, 0.05, 1)

        bag = conn.execute(
            "SELECT o.minimum_quantity, o.quantity_increment, o.quantity_is_decimal "
            "FROM source_offer o JOIN source_variant v USING (source_variant_id) "
            "WHERE v.external_variant_id = 'QzE1OTI='").fetchone()
        assert (bag[0], bag[1], bag[2]) == (450.0, 450.0, 0)

        stock = conn.execute(
            "SELECT p.stock_quantity FROM price_observation p "
            "JOIN source_offer o USING (offer_id) "
            "JOIN source_variant v USING (source_variant_id) "
            "WHERE v.external_variant_id = 'Tjcy'").fetchone()
        assert stock[0] == 8
    finally:
        conn.close()


def test_has_variants_stops_saying_one_for_everything(tmp_path):
    """P6. A simple product is emitted as row(uid, uid), so the old test
    (`external_variant_id or option_fingerprint`) read 1 for 763 of 763 MADAR
    products. A product that IS its own variant has no variations."""
    conn = _ingest(tmp_path)
    try:
        flags = dict(conn.execute(
            "SELECT external_product_id, has_variants FROM source_product"))
        assert flags["UFVUVFk="] == 0, "a simple product has no variations"
        assert flags["SFNT"] == 1
        assert flags["UkNG"] == 1
        assert set(flags.values()) != {1}, "the column must stop answering 1 for everything"
    finally:
        conn.close()


def test_an_offer_learns_the_quantity_facts_without_being_split(tmp_path):
    """The 0052 trap, avoided: all 3,417 MADAR offers already exist, so an
    INSERT-only path would leave every one of them blank forever. And none of
    these columns is in ux_source_offer_identity, so learning them must not
    mint a second offer beside the first."""
    conn = _ingest(tmp_path)
    try:
        before = conn.execute("SELECT COUNT(*) FROM source_offer").fetchone()[0]
        conn.execute("UPDATE source_offer SET minimum_quantity = NULL, "
                     "quantity_increment = NULL, quantity_is_decimal = 0")
        conn.commit()
        tables = [t for t in MagentoGraphqlConnector(_Fetcher()).fetch(_entry())
                  if t.kind == ExtractKind.PRODUCT_PRICES]
        ingest_payloads(conn, _entry(), [FunnelPayload(
            payload_version=PAYLOAD_VERSION, source_key="MADAR",
            kind=ExtractKind.PRODUCT_PRICES, client="cli",
            scraped_at="2026-07-30T10:00:00Z", source_url=t.source_url,
            header=t.header, rows=t.rows) for t in tables])
        assert conn.execute("SELECT COUNT(*) FROM source_offer").fetchone()[0] == before
        relearned = conn.execute(
            "SELECT o.minimum_quantity, o.quantity_is_decimal "
            "FROM source_offer o JOIN source_variant v USING (source_variant_id) "
            "WHERE v.external_variant_id = 'TjY1'").fetchone()
        assert (relearned[0], relearned[1]) == (0.25, 1)
    finally:
        conn.close()


def _payloads_through_a_file(tmp_path: Path, scraped_at: str) -> list[FunnelPayload]:
    """The payloads a crawl really ingests: SERIALIZED to disk and read back.

    The in-memory path is what the 0056 tests exercised, and it is the reason
    this defect shipped green — so the round trip is the shape asserted here.
    """
    payloads = []
    for i, t in enumerate(MagentoGraphqlConnector(_Fetcher()).fetch(_entry())):
        if t.kind != ExtractKind.PRODUCT_PRICES:
            continue
        written = FunnelPayload(
            payload_version=PAYLOAD_VERSION, source_key="MADAR",
            kind=ExtractKind.PRODUCT_PRICES, client="cli",
            scraped_at=scraped_at, source_url=t.source_url,
            header=t.header, rows=t.rows)
        path = tmp_path / f"madar-prices-{i}.json"
        path.write_text(written.model_dump_json(), encoding="utf-8")
        payloads.append(FunnelPayload.model_validate_json(
            path.read_text(encoding="utf-8")))
    return payloads


def test_the_payload_written_to_disk_still_carries_display_method(tmp_path):
    """The header the crawl WRITES, not the one the current spec would build."""
    payload = _payloads_through_a_file(tmp_path, "2026-07-30T10:00:00Z")[0]
    assert "display_method" in payload.header
    assert len(payload.header) == len(PRODUCT_PRICES.columns)
    view = RowView(PRODUCT_PRICES, payload.header)
    assert {view.get(row, "display_method") for row in payload.rows} == {
        DisplayMethod.MEMBER_LIST.value, DisplayMethod.OPTIONS_PRICED.value,
        DisplayMethod.OPTIONS_ONE_PRICE.value, DisplayMethod.SINGLE.value}


def test_a_product_that_already_exists_learns_display_method(tmp_path):
    """THE DEFECT THIS FILE SHIPPED. All 763 MADAR products were first seen
    2026-07-25..27, days before display_method existed, so every one of them
    takes the UPDATE path and NOT the INSERT that writes the column. Three
    successful `update` crawls later the column was empty on all 763 and
    change_event held 0 display_method rows.

    The cause was not the connector, the payload or the diff — each of those
    was verified working. It was ingest._with_product_sku narrowing the row to
    a HAND-LISTED tuple of keys that was never extended with display_method, so
    product_field_diffs was handed a dict in which the field could not differ.
    The sibling test above passes on a FRESH database, where every product is
    inserted; only a second ingest can see this.
    """
    conn = dbmod.connect(tmp_path / "harvest.db")
    try:
        dbmod.migrate(conn)
        ingest_payloads(conn, _entry(),
                        _payloads_through_a_file(tmp_path, "2026-07-29T10:00:00Z"))

        # Seed the warehouse to look like the live one: every product already
        # exists, was first seen BEFORE display_method was a column (the real
        # min first_seen is 2026-07-25T06:57:29Z), and the column is empty. The
        # first_seen date is cosmetic to path selection — INSERT vs UPDATE turns
        # on the row already existing — but it is the shape the owner describes,
        # and empty-on-existing-rows is precisely what broke.
        conn.execute("UPDATE source_product SET display_method = '', "
                     "first_seen_at = '2026-07-25T06:57:29Z'")
        conn.commit()
        before = conn.execute("SELECT COUNT(*) FROM source_product").fetchone()[0]
        assert conn.execute(
            "SELECT MAX(first_seen_at) FROM source_product").fetchone()[0] \
            < "2026-07-29", "the seed must predate the column to exercise UPDATE"
        assert not any(v for _, v in conn.execute(
            "SELECT external_product_id, display_method FROM source_product")), \
            "the seed must start with the column empty on every row"

        ingest_payloads(conn, _entry(),
                        _payloads_through_a_file(tmp_path, "2026-07-30T10:00:00Z"))

        shapes = dict(conn.execute(
            "SELECT external_product_id, display_method FROM source_product"))
        assert shapes == {"SFNT": DisplayMethod.MEMBER_LIST.value,
                          "UkNG": DisplayMethod.OPTIONS_PRICED.value,
                          "TEVH": DisplayMethod.OPTIONS_ONE_PRICE.value,
                          "UFVUVFk=": DisplayMethod.SINGLE.value}
        # The owner's report format: the count per value. Each of the four live
        # shapes is present exactly once in the fixture, so the breakdown the
        # owner will read off the 763 (single 400 / options_one_price 36 /
        # options_priced 292 / member_list 33) is exercised here as 1 / 1 / 1 / 1
        # with zero left empty — the same UPDATE path, at fixture scale.
        breakdown = dict(conn.execute(
            "SELECT display_method, COUNT(*) FROM source_product "
            "GROUP BY display_method ORDER BY display_method"))
        assert breakdown == {DisplayMethod.MEMBER_LIST.value: 1,
                             DisplayMethod.OPTIONS_ONE_PRICE.value: 1,
                             DisplayMethod.OPTIONS_PRICED.value: 1,
                             DisplayMethod.SINGLE.value: 1}
        assert "" not in breakdown, "no pre-existing product may be left empty"
        # Learning a column must not mint a second product beside the first.
        assert conn.execute(
            "SELECT COUNT(*) FROM source_product").fetchone()[0] == before
        # And the learning is an EVENT, like every other tracked field's.
        assert conn.execute(
            "SELECT COUNT(*) FROM change_event "
            "WHERE field_key = 'display_method'").fetchone()[0] == len(shapes)
    finally:
        conn.close()


def test_every_tracked_product_field_can_actually_be_updated():
    """The guard on the class of defect, not just this instance.

    _with_product_sku builds the ONLY dict product_field_diffs ever reads, so a
    tracked field missing from it is tracked-but-frozen — and nothing raises:
    the column just silently keeps its old value forever. Adding a pair to
    TRACKED_PRODUCT_FIELDS must be the whole change.
    """
    from scrapex.changes import TRACKED_PRODUCT_FIELDS
    from scrapex.ingest import _with_product_sku

    # Asserted against the PUBLIC behaviour of _with_product_sku, not against
    # the constant that implements it: this test has to be able to fail on the
    # hand-listed version too, and an ImportError is not this defect's shape.
    reachable = set(_with_product_sku({}))
    tracked = {row_key for _, row_key in TRACKED_PRODUCT_FIELDS}
    assert tracked - reachable == set(), (
        f"tracked but unreachable by the diff: {sorted(tracked - reachable)}")


def test_migration_0056_corrects_has_variants_on_rows_that_already_exist():
    """The backfill, on a warehouse that predates it.

    ingest only ever wrote has_variants at INSERT, so fixing the rule there
    corrects products discovered from now on and leaves every EXISTING one
    reading 1 — all 763 MADAR products and every product of sources
    1,2,3,4,7,8,9. A column that is right for new rows and wrong for old ones
    is worse than one that is uniformly wrong, because nothing on screen says
    which kind of row you are looking at. Unlike the other three columns this
    one is derivable from rows the warehouse already holds, so it is the one
    thing in 0056 that can be — and is — repaired in place.
    """
    conn = dbmod.connect(":memory:")
    try:
        for number, file in dbmod._migration_files():      # the pre-0056 warehouse
            if number >= 56:
                continue
            conn.executescript(file.read_text(encoding="utf-8"))
            conn.execute(f"PRAGMA user_version = {number}")
        conn.execute("INSERT INTO source_site (source_id, source_key, source_name_ar)"
                     " VALUES (1, 'MADAR', 'المدار')")
        # Both stored the way ingest really stored them: has_variants = 1,
        # because external_variant_id was never empty for either.
        for pid, ext in ((1, "SIMPLE"), (2, "GROUPED")):
            conn.execute("INSERT INTO source_product"
                         " (source_product_id, source_id, external_product_id, has_variants)"
                         " VALUES (?, 1, ?, 1)", (pid, ext))
        # A simple product is one variant wearing the PRODUCT's own id...
        conn.execute("INSERT INTO source_variant (source_product_id, external_variant_id)"
                     " VALUES (1, 'SIMPLE')")
        # ...while a grouped product's members carry ids of their own.
        for member in ("MEMBER-8", "MEMBER-32"):
            conn.execute("INSERT INTO source_variant (source_product_id, external_variant_id)"
                         " VALUES (2, ?)", (member,))
        conn.commit()

        assert dbmod.migrate(conn) == [56, 57]

        flags = dict(conn.execute(
            "SELECT external_product_id, has_variants FROM source_product"))
        assert flags["SIMPLE"] == 0, (
            "a product whose only variant IS itself has no variations")
        assert flags["GROUPED"] == 1
    finally:
        conn.close()


def test_a_connector_that_says_nothing_never_blanks_what_was_learned(tmp_path):
    """The empty-value rule. A payload from a connector that has not been
    taught these columns must not wipe values an earlier crawl stored."""
    from scrapex.ingest import _quantity_facts
    assert _quantity_facts({}) == {}
    assert _quantity_facts({"minimum_quantity": "", "quantity_increment": "",
                            "quantity_is_decimal": ""}) == {}
    # ...while a site that really says "not a decimal quantity" is recorded.
    assert _quantity_facts({"quantity_is_decimal": "0"}) == {"quantity_is_decimal": 0}
