"""T2: magento-graphql connector against a recorded madar-shaped GraphQL response."""
from __future__ import annotations

import json
import json as _json
import sqlite3
from pathlib import Path

from scrapex import db as dbmod
from scrapex.config import ExtractSpec, SourceEntry
from scrapex.connectors.magento import MagentoGraphqlConnector
from scrapex.ingest import ingest_payloads
from scrapex.rowspec import PRODUCT_PRICES, RowView
from scrapex.vocab import ExtractKind, ExtractScope

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "magento_products.json").read_text(encoding="utf-8"))


class _StubResponse:
    def __init__(self, payload): self._payload = payload
    def json(self): return self._payload


class _StubFetcher:
    """Serves the fixture on page 1, an empty page after (ends pagination).
    The tree walk sees an empty tree — classification comes from the product
    payloads themselves, the stock-Magento path."""
    def __init__(self): self.requests_count = 0
    def post(self, url, json=None, **kwargs):
        self.requests_count += 1
        if (kwargs.get("headers") or {}).get("Store"):
            # the en_SA pass: this stub models a monolingual store
            return _StubResponse({"data": {"products": {
                "items": [], "page_info": {"total_pages": 1}}}})
        query = (json or {}).get("query", "")
        if "categoryList" in query:
            return _StubResponse({"data": {"categoryList": [{"children": []}]}})
        page = (json or {}).get("variables", {}).get("currentPage", 1)
        return _StubResponse(FIXTURE if page == 1 else {"data": {"products": {"items": []}}})
    def close(self): pass


class _CensusBlindFetcher(_StubFetcher):
    """The madar shape, verified live 2026-07-22: the price-filtered census
    answers categories:[] on every product while the category tree and the
    per-category listings are fully populated."""
    TREE = {"data": {"categoryList": [{"children": [
        {"uid": "Mw==", "name": "المعادن والحديد الإنشائي", "children": [
            {"uid": "NA==", "name": "حديد التسليح والشبك", "children": []},
        ]},
        {"uid": "MTg=", "name": "مواد البناء ولوازم الموقع", "children": [
            {"uid": "MjA=", "name": "الأسمنت والجبس", "children": []},
        ]},
    ]}]}}
    # The plywood product files in BOTH leaves; a longer path always wins, a
    # tie keeps the first-walked home.
    LEAVES = {
        "NA==": ["NDY3Mg=="],
        "MjA=": ["NDY3Mg==", "Q0VNQg=="],
    }

    def post(self, url, json=None, **kwargs):
        self.requests_count += 1
        if (kwargs.get("headers") or {}).get("Store"):
            return _StubResponse({"data": {"products": {
                "items": [], "page_info": {"total_pages": 1}}}})
        query = (json or {}).get("query", "")
        variables = (json or {}).get("variables", {})
        if "categoryList" in query:
            return _StubResponse(self.TREE)
        if "category_uid" in query:
            uids = self.LEAVES.get(variables.get("uid"), [])
            return _StubResponse({"data": {"products": {
                "items": [{"uid": u} for u in uids],
                "page_info": {"current_page": 1, "total_pages": 1}}}})
        page = variables.get("currentPage", 1)
        if page != 1:
            return _StubResponse({"data": {"products": {"items": []}}})
        blind = _json.loads(_json.dumps(FIXTURE))
        for item in blind["data"]["products"]["items"]:
            item["categories"] = []                  # what madar actually answers
        return _StubResponse(blind)


def make_entry() -> SourceEntry:
    return SourceEntry.model_validate(dict(
        source_key="MADAR", source_name="المدار", base_url="https://www.madar.com",
        family="magento-graphql", currency="SAR", default_region="SA", vat_mode="excl",
        extract=[ExtractSpec(kind=ExtractKind.PRODUCT_PRICES, scope=ExtractScope.CENSUS)],
    ))


def test_magento_maps_variants_and_simple():
    table = next(iter(MagentoGraphqlConnector(_StubFetcher()).fetch(make_entry())))
    assert table.header == list(PRODUCT_PRICES.columns)
    assert len(table.rows) == 4  # 2 variants + 1 simple + 1 cement variant

    view = RowView(PRODUCT_PRICES, table.header)
    v12 = view.as_dict(table.rows[0])
    assert v12["external_product_id"] == "NDY3Mg=="       # parent uid
    assert v12["external_variant_id"] == "NDY3MA=="        # child uid — the owner's key rule
    assert v12["external_sku"] == "120151248"
    assert v12["price"] == "112.5"
    assert v12["option_fingerprint"] == "thickness_mm=12"
    assert v12["currency"] == "SAR" and v12["country_code_alpha2"] == "SA" and v12["tax_included"] == "0"

    v18 = view.as_dict(table.rows[1])
    assert v18["price"] == "168.78" and v18["price_before"] == "200.0"  # on sale
    assert v18["price_sale"] == "168.78"

    simple = view.as_dict(table.rows[2])
    assert simple["external_product_id"] == simple["external_variant_id"] == "Q0VNQg=="
    assert simple["availability"] == "out_of_stock"


def test_magento_end_to_end_into_warehouse():
    entry = make_entry()
    table = next(iter(MagentoGraphqlConnector(_StubFetcher()).fetch(entry)))
    conn: sqlite3.Connection = dbmod.connect(":memory:")
    try:
        dbmod.migrate(conn)
        result = ingest_payloads(conn, entry, [table.to_payload()])
    finally:
        conn.close()
    assert result.observations == 4 and result.products == 3 and result.variants == 4
    assert not result.errors


def test_the_deepest_filing_is_the_classification_that_rides_every_row():
    """Madar files one product under a shallow promo bucket AND its real
    three-level home; the levels are the information (owner ruling), so the
    deepest chain wins and travels on every variant row of the product."""
    table = next(iter(MagentoGraphqlConnector(_StubFetcher()).fetch(make_entry())))
    view = RowView(PRODUCT_PRICES, table.header)

    for variant_row in table.rows[:2]:            # both variants of product 1
        row = view.as_dict(variant_row)
        assert row["category_path_ar"] == "مواد البناء > الأخشاب > أخشاب معالجة"
        assert row["category_external_id"] == "Q0FULTQ0"

    simple = view.as_dict(table.rows[2])
    assert simple["category_path_ar"] == "أسمنت"     # one flat filing, one level
    assert simple["category_external_id"] == "Q0FULTc="


def test_classification_lands_on_the_product_and_reaches_the_main_table():
    entry = make_entry()
    table = next(iter(MagentoGraphqlConnector(_StubFetcher()).fetch(entry)))
    conn: sqlite3.Connection = dbmod.connect(":memory:")
    try:
        dbmod.migrate(conn)
        ingest_payloads(conn, entry, [table.to_payload()])

        stored = dict(conn.execute(
            "SELECT external_product_id, category_path_ar FROM source_product").fetchall())
        assert stored["NDY3Mg=="] == "مواد البناء > الأخشاب > أخشاب معالجة"

        from scrapex.reports import table_payload
        grid = table_payload(conn, "MADAR")
        keys = {c["key"] for c in grid["columns"]}
        # Three levels published -> exactly L1..L3 offered, never an empty L4.
        # This stub is a MONOLINGUAL store, so the Arabic-marked columns are
        # the ones it fills and the unmarked English ones are absent.
        assert {"category_ar", "category_l1_ar", "category_l2_ar",
                "category_l3_ar"} <= keys
        assert "category_l4_ar" not in keys
        plywood = next(r for r in grid["rows"]
                       if r["product_name_ar"].startswith("Fire Retardant"))
        assert plywood["category_ar"] == "مواد البناء > الأخشاب > أخشاب معالجة"
        assert plywood["category_l1_ar"] == "مواد البناء"
        assert plywood["category_l2_ar"] == "الأخشاب"
        assert plywood["category_l3_ar"] == "أخشاب معالجة"
        cement = next(r for r in grid["rows"] if r["category_ar"] == "أسمنت")
        assert cement["category_l1_ar"] == "أسمنت" and cement["category_l2_ar"] == ""
    finally:
        conn.close()


def test_a_product_the_site_refiles_records_the_move():
    """Classification is tracked like brand: a re-filed product must record
    FIELD_UPDATED with both values, not silently forget its old home."""
    entry = make_entry()
    conn: sqlite3.Connection = dbmod.connect(":memory:")
    try:
        dbmod.migrate(conn)
        table = next(iter(MagentoGraphqlConnector(_StubFetcher()).fetch(entry)))
        ingest_payloads(conn, entry, [table.to_payload()])

        moved = json.loads(json.dumps(FIXTURE))          # deep copy, then re-file
        target = next(i for i in moved["data"]["products"]["items"]
                      if i["uid"] == "Q0VNQg==")
        target["categories"] = [
            {"uid": "Q0FULTg=", "name": "مواد لاصقة",
             "breadcrumbs": [{"category_name": "مواد البناء"}]}]

        class _MovedFetcher(_StubFetcher):
            def post(self, url, json=None, **kwargs):
                page = (json or {}).get("variables", {}).get("currentPage", 1)
                return _StubResponse(moved if page == 1
                                     else {"data": {"products": {"items": []}}})

        table2 = next(iter(MagentoGraphqlConnector(_MovedFetcher()).fetch(entry)))
        ingest_payloads(conn, entry, [table2.to_payload()])

        path = conn.execute(
            "SELECT category_path_ar FROM source_product WHERE product_name_ar LIKE '%Cement%' "
            "OR external_product_id = 'Q0VNQg=='").fetchone()[0]
        assert path == "مواد البناء > مواد لاصقة"
        event = conn.execute(
            "SELECT previous_value, new_value FROM change_event "
            # The STORED column: change_event records the warehouse's own
            # vocabulary, which since 0038 says which language it holds. The
            # wire key is still `category_path` and still carries Arabic.
            "WHERE field_key = 'category_path_ar'").fetchone()
        assert event is not None, "the re-filing left no change event"
        assert event[0] == "أسمنت" and event[1] == "مواد البناء > مواد لاصقة"
    finally:
        conn.close()


def test_a_census_that_hides_categories_gets_them_from_the_tree_walk():
    """Verified live: madar's price census answers categories:[] on every
    product while the tree knows the real home. The walk knows each leaf's
    full path, and a product filed in two leaves keeps the DEEPEST one."""
    fetcher = _CensusBlindFetcher()
    table = next(iter(MagentoGraphqlConnector(fetcher).fetch(make_entry())))
    view = RowView(PRODUCT_PRICES, table.header)

    plywood = view.as_dict(table.rows[0])
    # Both walked homes are two levels; the tie keeps the first-walked, and
    # either way BOTH levels arrive — never the census's empty answer.
    assert plywood["category_path_ar"] == "المعادن والحديد الإنشائي > حديد التسليح والشبك"
    assert plywood["category_external_id"] == "NA=="
    cement = view.as_dict(table.rows[2])
    assert cement["category_path_ar"] == "مواد البناء ولوازم الموقع > الأسمنت والجبس"


def test_a_dead_tree_walk_costs_a_note_never_the_price_crawl():
    class _TreeDownFetcher(_StubFetcher):
        def post(self, url, json=None, **kwargs):
            if "categoryList" in (json or {}).get("query", ""):
                self.requests_count += 1
                raise RuntimeError("503 service unavailable")
            return super().post(url, json=json, **kwargs)

    table = next(iter(MagentoGraphqlConnector(_TreeDownFetcher()).fetch(make_entry())))

    assert len(table.rows) == 4, "the prices must survive a dead tree walk"
    assert any("category tree walk failed" in w for w in table.warnings)


# ---- selling units, option meaning, both languages (owner memo 2026-07-23) ---

def test_variant_axes_carry_their_names_not_bare_numbers():
    """"2.2, 24, 24, 6000" was unreadable; configurable_options carries the
    site's own label per axis, and the option label says both."""
    table = next(iter(MagentoGraphqlConnector(_StubFetcher()).fetch(make_entry())))
    view = RowView(PRODUCT_PRICES, table.header)

    v12 = view.as_dict(table.rows[0])
    assert v12["variant_ar"] == "السماكة (مم): 12"


def test_the_stated_basis_rides_the_price_and_a_piece_mass_does_not():
    """Riyadh-cement shape: weight 50 AND "50كجم" in the name agree — the
    price is per 50 kg, from the source's own statement. The plywood's 6.72
    is the PIECE's mass with no stated quantity: inventing "per 6.72 kg"
    is exactly the guess the rule refuses."""
    table = next(iter(MagentoGraphqlConnector(_StubFetcher()).fetch(make_entry())))
    view = RowView(PRODUCT_PRICES, table.header)

    cement = view.as_dict(table.rows[3])
    assert cement["unit"] == "kg" and cement["basis_quantity"] == "50"
    assert cement["variant_ar"] == "نوع الأسمنت: اسمنت ابيض"

    plywood = view.as_dict(table.rows[0])
    assert plywood["unit"] == "" and plywood["basis_quantity"] == ""


def test_english_names_ride_every_row_when_the_store_answers():
    """Both languages, one crawl (owner ruling): the en_SA pass maps uids to
    English names and the rows carry them beside the primary name."""
    class _BilingualFetcher(_StubFetcher):
        def post(self, url, json=None, **kwargs):
            if (kwargs.get("headers") or {}).get("Store") == "en_SA":
                self.requests_count += 1
                return _StubResponse({"data": {"products": {
                    "items": [
                        {"uid": "NDY3Mg==", "name": "Fire Retardant Plywood",
                         "variants": [
                             {"product": {"uid": "NDY3MA==",
                                          "name": "Fire Retardant Plywood - 12mm"}}]},
                        {"uid": "Q0VNMg==", "name": "Madar Cement",
                         "variants": [
                             {"product": {"uid": "Q0VNMy==",
                                          "name": "White Cement - 50kg"}}]},
                    ],
                    "page_info": {"total_pages": 1}}}})
            return super().post(url, json=json, **kwargs)

    table = next(iter(MagentoGraphqlConnector(_BilingualFetcher()).fetch(make_entry())))
    view = RowView(PRODUCT_PRICES, table.header)

    # The PRODUCT's English name, not the child's — madar names its variant
    # children by internal SKU string in both stores, so asking the child
    # first put a part number where the page shows a product name
    # (owner-reported after the first bilingual crawl).
    v12 = view.as_dict(table.rows[0])
    assert v12["product_name"] == "Fire Retardant Plywood"
    cement = view.as_dict(table.rows[3])
    assert cement["product_name"] == "Madar Cement"

    conn: sqlite3.Connection = dbmod.connect(":memory:")
    try:
        dbmod.migrate(conn)
        table2 = next(iter(MagentoGraphqlConnector(_BilingualFetcher()).fetch(make_entry())))
        ingest_payloads(conn, make_entry(), [table2.to_payload()])
        stored = conn.execute(
            "SELECT product_name FROM source_product "
            "WHERE external_product_id = 'Q0VNMg=='").fetchone()[0]
        assert stored == "Madar Cement"

        from scrapex.reports import table_payload
        grid = table_payload(conn, "MADAR")
        columns = {c["key"]: c["label"] for c in grid["columns"]}
        assert "product_name" in columns, \
            "a bilingual source must offer the English name column"
        # The mark is a property of the COLUMN, not of the pair: it is
        # authored into the label rather than appended when a twin happens
        # to be present.
        assert columns["product_name_ar"] == "Product name (AR)"
    finally:
        conn.close()


def test_a_monolingual_source_never_sees_the_english_column():
    conn: sqlite3.Connection = dbmod.connect(":memory:")
    try:
        dbmod.migrate(conn)
        table = next(iter(MagentoGraphqlConnector(_StubFetcher()).fetch(make_entry())))
        ingest_payloads(conn, make_entry(), [table.to_payload()])

        from scrapex.reports import table_payload
        grid = table_payload(conn, "MADAR")
        columns = {c["key"]: c["label"] for c in grid["columns"]}
        assert "product_name" not in columns
        # The assertion this test was always missing: the ONE name column a
        # monolingual source shows still says which language it holds. It used
        # to read a plain "Record", because the "(AR)" was runtime-conditional
        # on a twin that does not exist here.
        assert columns["product_name_ar"] == "Product name (AR)"
    finally:
        conn.close()


def test_enrichment_stays_dormant_until_the_manifest_asks():
    tables = list(MagentoGraphqlConnector(_StubFetcher()).fetch(make_entry()))
    assert len(tables) == 1, "enrichment emitted without a manifest declaration"


def test_the_more_information_panel_lands_as_enrichment_when_asked():
    """manufacturer / origin / size / grade — the site's "المزيد من المعلومات"
    panel, verified live via custom_attributesV2 (2026-07-23). Dropdowns
    arrive as selected_options; both value shapes land as stated facts."""
    from scrapex.rowspec import ENRICHMENT

    entry = SourceEntry.model_validate(dict(
        source_key="MADAR", source_name="المدار", base_url="https://www.madar.com",
        family="magento-graphql", currency="SAR", default_region="SA", vat_mode="excl",
        extract=[ExtractSpec(kind=ExtractKind.PRODUCT_PRICES, scope=ExtractScope.CENSUS),
                 ExtractSpec(kind=ExtractKind.ENRICHMENT, scope=ExtractScope.CENSUS)],
    ))
    tables = list(MagentoGraphqlConnector(_StubFetcher()).fetch(entry))
    assert len(tables) == 2, "the manifest asked and no enrichment came"

    view = RowView(ENRICHMENT, tables[1].header)
    rows = [view.as_dict(r) for r in tables[1].rows]
    by_code = {r["attribute_code"]: r for r in rows if r["external_product_id"] == "Q0VNMg=="}
    # This stub answers the DEFAULT store only, which serves Arabic — so
    # every fact lands under its _ar code with lang declared, and the bare
    # English codes are absent rather than filled with the wrong language.
    # The code and the lang beside it say the same thing (0039/0045).
    assert by_code["manufacturer_ar"]["raw_value"] == "اسمنت الرياض"
    assert by_code["manufacturer_ar"]["lang"] == "ar"
    assert "manufacturer" not in by_code, \
        "an unmarked code must never carry the Arabic edition"
    assert by_code["grade_ar"]["raw_value"] == "A500"       # dropdown -> label
    assert by_code["size_ar"]["raw_value"] == "50 Kg"
    assert by_code["manufacturer_ar"]["attribute_group"] == "More information"
    assert "توفر شركة" in by_code["short_description_ar"]["raw_value"]
    # The plywood piece-mass rides as a weight measurement (not a unit).
    weights = [r for r in rows if r["attribute_code"] == "weight"]
    assert weights and all(r["unit_raw"] == "kg" for r in weights)


def test_the_deeper_home_wins_over_a_longer_shallow_name():
    """'Deepest wins' means LEVELS, not characters: a one-level promo bucket
    with a long Arabic name must never beat a stated three-level home
    (adversarial review, reproduced by execution)."""
    from scrapex.connectors.magento import MagentoGraphqlConnector, _depth

    assert _depth("") == 0 and _depth("أسمنت") == 1 and _depth("a > b > c") == 3

    from scrapex.rowspec import RowBuilder
    builder = RowBuilder(PRODUCT_PRICES)
    product = {
        "uid": "P1", "sku": "s", "name": "n", "url_key": "u",
        "stock_status": "IN_STOCK",
        "categories": [{"uid": "C3", "name": "حديد",
                        "breadcrumbs": [{"category_name": "مواد"},
                                        {"category_name": "معادن"}]}],
        "price_range": {"minimum_price": {"regular_price": {"value": 10.0},
                                          "final_price": {"value": 10.0}}},
    }
    ctx = {"base": "https://x", "currency": "SAR", "vat": "0", "country_code_alpha2": "SA",
           "paths": {"P1": ("التخفيضات والعروض الحصرية الكبرى للمقاولين", "PROMO")}}

    rows = MagentoGraphqlConnector._product_rows(builder, product, ctx)
    row = RowView(PRODUCT_PRICES, builder.header).as_dict(rows[0])
    assert row["category_path_ar"] == "مواد > معادن > حديد"
    assert row["category_external_id"] == "C3"


def test_the_api_price_is_the_price_and_no_tax_is_ever_invented():
    """The uplift this test once defended, then guarded, is GONE.

    Its history: the owner saw 224.14 on the Legrand page the same day a sample
    answered 194.9, and 194.9 x 1.15 = 224.135, so a source-wide 15% multiply
    was added. It made 3,312 rows wrong. The owner's ruling replaced the
    mechanism outright — «سجلها كما تاخذ البيانات من الموقع بدون تعديل» — so
    _prices takes no rate at all now. The signature IS the guarantee: a caller
    cannot pass one, and this test fails loudly if the parameter comes back.
    """
    import inspect

    from scrapex.connectors.magento import _prices

    node = {"price_range": {"minimum_price": {"regular_price": {"value": 224.14},
                                              "final_price": {"value": 224.14}}}}
    assert _prices(node) == (224.14, 224.14)

    assert list(inspect.signature(_prices).parameters) == ["node"], \
        "a rate parameter on _prices is an uplift waiting to be declared"


def test_the_row_carries_the_products_localized_name_never_the_child_sku_string():
    """madar's variant child is named by its internal SKU string, identical in
    both stores, while the product carries the real localized name. Storing the
    child's put an English code where the page shows Arabic and contradicted
    the row's own variant label."""
    from scrapex.connectors.magento import MagentoGraphqlConnector
    from scrapex.rowspec import RowBuilder

    builder = RowBuilder(PRODUCT_PRICES)
    product = {
        "uid": "P1", "sku": "kit", "name": "علب أرضية منبثقة من ليجراند",
        "url_key": "legrand-pop-up-floor-box-kit", "stock_status": "IN_STOCK",
        "configurable_options": [{"attribute_code": "color", "label": "اللون"}],
        "variants": [{"product": {"uid": "V1", "sku": "054010",
                                  "name": "054010 FLOOR BACK BOX POPUP ALU 3MOD LEGRAND",
                                  "stock_status": "IN_STOCK",
                                  "price_range": {"minimum_price": {
                                      "regular_price": {"value": 194.9},
                                      "final_price": {"value": 194.9}}}},
                      "attributes": [{"code": "color", "label": "Aluminium"}]}],
    }
    ctx = {"base": "https://www.madar.com", "currency": "SAR", "vat": "1",
           "country_code_alpha2": "SA",
           "names_en": {"P1": "Legrand Pop-up Floor Box Kit"}}

    row = RowView(PRODUCT_PRICES, builder.header).as_dict(
        MagentoGraphqlConnector._product_rows(builder, product, ctx)[0])

    assert row["product_name_ar"] == "علب أرضية منبثقة من ليجراند"
    assert row["product_name"] == "Legrand Pop-up Floor Box Kit"
    assert row["variant_ar"] == "اللون: Aluminium"
    assert row["price"] == "194.9"      # the API figure, untouched


def test_the_english_tree_relabels_every_walked_path_for_one_query():
    """The standing bilingual rule, cheaply: leaf uids are store-independent,
    so ONE extra categoryList query in en_SA relabels every path the Arabic
    walk already found — no second product listing, no second crawl."""
    class _Bilingual(_CensusBlindFetcher):
        TREE_EN = {"data": {"categoryList": [{"children": [
            {"uid": "Mw==", "name": "Metals & structural steel", "children": [
                {"uid": "NA==", "name": "Rebar & mesh", "children": []}]},
            {"uid": "MTg=", "name": "Building materials", "children": [
                {"uid": "MjA=", "name": "Cement & gypsum", "children": []}]},
        ]}]}}

        def post(self, url, json=None, **kwargs):
            store = (kwargs.get("headers") or {}).get("Store")
            query = (json or {}).get("query", "")
            if store == "en_SA" and "categoryList" in query:
                self.requests_count += 1
                return _StubResponse(self.TREE_EN)
            return super().post(url, json=json, **kwargs)

    table = next(iter(MagentoGraphqlConnector(_Bilingual()).fetch(make_entry())))
    view = RowView(PRODUCT_PRICES, table.header)
    row = view.as_dict(table.rows[0])

    assert row["category_path_ar"] == "المعادن والحديد الإنشائي > حديد التسليح والشبك"
    assert row["category_path"] == "Metals & structural steel > Rebar & mesh"


def test_a_missing_english_tree_costs_a_note_never_the_classification():
    class _NoEnglishTree(_CensusBlindFetcher):
        def post(self, url, json=None, **kwargs):
            if (kwargs.get("headers") or {}).get("Store") == "en_SA" \
                    and "categoryList" in (json or {}).get("query", ""):
                self.requests_count += 1
                raise RuntimeError("503 service unavailable")
            return super().post(url, json=json, **kwargs)

    table = next(iter(MagentoGraphqlConnector(_NoEnglishTree()).fetch(make_entry())))
    view = RowView(PRODUCT_PRICES, table.header)

    assert view.as_dict(table.rows[0])["category_path_ar"], "the Arabic path must survive"
    assert any("english category tree" in w for w in table.warnings)


# ---------------------------------------------------------------------------
# B1 (2026-07-25): madar publishes THREE product shapes, and they do not share
# one price rule. The fixture below is a live capture — see
# tests/fixtures/live/madar_shapes_2026-07-25.CAPTURE.md for the census counts
# (399 simple / 328 configurable / 33 grouped) and the storefront evidence.
# ---------------------------------------------------------------------------

SHAPES = json.loads((Path(__file__).parent / "fixtures" / "live" /
                     "madar_shapes_2026-07-25.json").read_text(encoding="utf-8"))


class _ShapesFetcher(_StubFetcher):
    """The four live shapes on page 1; no tree, no English store."""

    def post(self, url, json=None, **kwargs):
        self.requests_count += 1
        if (kwargs.get("headers") or {}).get("Store"):
            return _StubResponse({"data": {"products": {
                "items": [], "page_info": {"total_pages": 1}}}})
        query = (json or {}).get("query", "")
        if "categoryList" in query:
            return _StubResponse({"data": {"categoryList": [{"children": []}]}})
        page = (json or {}).get("variables", {}).get("currentPage", 1)
        return _StubResponse(SHAPES if page == 1
                             else {"data": {"products": {"items": []}}})


def shapes_entry(**api) -> SourceEntry:
    spec = dict(
        source_key="MADAR", source_name="المدار", base_url="https://www.madar.com",
        family="magento-graphql", currency="SAR", default_region="SA",
        vat_mode="incl",
        extract=[ExtractSpec(kind=ExtractKind.PRODUCT_PRICES, scope=ExtractScope.CENSUS)],
    )
    if api:
        spec["api"] = api
    return SourceEntry.model_validate(spec)


def _shape_rows(entry=None):
    table = next(iter(MagentoGraphqlConnector(_ShapesFetcher())
                      .fetch(entry or shapes_entry())))
    view = RowView(PRODUCT_PRICES, table.header)
    return table, [view.as_dict(r) for r in table.rows]


def test_a_grouped_product_becomes_one_row_per_member_not_one_row_per_group():
    """The Swedish redwood group is 28 different boards, priced separately.

    The storefront page prints NO price for the group — it prints
    «المقاسات/الأنواع المتوفرة» and then one figure per member, and those
    figures are the API's member prices to the piastre. Storing one row at the
    group's minimum said "Swedish redwood costs 1,449" about a product whose
    boards run to 2,233.88.
    """
    _table, rows = _shape_rows()
    members = [r for r in rows if r["product_name_ar"] == "الخشب الأحمر السويدي"]
    assert len(members) == 4, "one row per member of the captured group"
    assert {r["price"] for r in members} == {
        "1630.13", "1750.88", "1811.25", "1449"}
    # Each row is a distinct offer, identified by the member, and labelled with
    # the member name the page prints beside that member's price.
    assert len({r["external_variant_id"] for r in members}) == 4
    assert len({r["external_sku"] for r in members}) == 4
    assert all(r["variant_ar"].startswith("خشب سويدي") for r in members)
    # The GROUP still owns the rows: one product, several offers.
    assert len({r["external_product_id"] for r in members}) == 1


def test_the_groups_maximum_price_is_a_lie_the_connector_must_not_believe():
    """Magento answers maximum_price == minimum_price on EVERY one of madar's
    33 grouped products, including this one whose members span 1449..1811.25 in
    the capture (1449..2233.88 live). A range check on the group would pass and
    the group figure would still be one member's price under the group's name,
    so the members — not the group — are what gets read."""
    group = next(i for i in SHAPES["data"]["products"]["items"]
                 if i["sku"] == "11535-SRW")
    span = group["price_range"]
    assert span["minimum_price"]["final_price"]["value"] == 1449
    assert span["maximum_price"]["final_price"]["value"] == 1449, "the lie itself"
    member_prices = [m["product"]["price_range"]["minimum_price"]["final_price"]["value"]
                     for m in group["items"]]
    assert max(member_prices) > min(member_prices), "the members really do differ"

    _table, rows = _shape_rows()
    priced = {r["price"] for r in rows
              if r["product_name_ar"] == "الخشب الأحمر السويدي"}
    assert "1811.25" in priced, "the dearer member must reach the table"


def test_a_grouped_product_whose_members_carry_no_price_is_skipped_out_loud():
    priceless = _json.loads(_json.dumps(SHAPES))
    for item in priceless["data"]["products"]["items"]:
        for member in item.get("items") or []:
            member["product"]["price_range"] = {"minimum_price": {}}

    class _Priceless(_ShapesFetcher):
        def post(self, url, json=None, **kwargs):
            answer = super().post(url, json=json, **kwargs)
            payload = answer.json()
            if ((payload.get("data") or {}).get("products") or {}).get("items"):
                return _StubResponse(priceless)
            return answer

    table = next(iter(MagentoGraphqlConnector(_Priceless()).fetch(shapes_entry())))
    view = RowView(PRODUCT_PRICES, table.header)
    assert not [r for r in table.rows
                if view.as_dict(r)["product_name_ar"] == "الخشب الأحمر السويدي"]
    assert any("grouped product" in w and "11535-SRW" in w for w in table.warnings)
    # And never at the group's own figure, which is what it used to fall back to.
    assert not [r for r in table.rows if view.as_dict(r)["price"] == "1449"]


def test_a_configurable_is_stored_at_the_api_figure_and_says_it_excludes_tax():
    """GraphQL answers 50.4 for 12512-TSP; the page prints 57.96.

    The page is not guessed at — it declares
    `finalPriceExclTaxKey = 'basePrice'` / `finalPriceInclTaxKey = 'finalPrice'`
    and then publishes `{"basePrice":{"amount":50.4},
    "finalPrice":{"amount":57.96}}`, so the API lands on the field the
    storefront itself calls tax-exclusive.

    The owner's rule for that is not arithmetic: record what the site gives and
    make the tax column say what it is. 50.4 goes in the row, tax_included=0
    goes beside it. 57.96 is never stored, because 57.96 is a number WE would
    have produced.
    """
    table, rows = _shape_rows(shapes_entry(configurable_prices_exclude_tax=True))
    plywood = [r for r in rows if r["product_name_ar"] == "Tigercore Shuttering Plywood"]
    assert len(plywood) == 2
    assert {r["price"] for r in plywood} == {"50.4", "90.3"}
    assert {r["price_before"] for r in plywood} == {"50.4", "90.3"}
    assert all(r["tax_included"] == "0" for r in plywood), \
        "the figure the shop calls basePrice must not claim to include tax"
    assert not any("57.96" in r["price"] for r in plywood), \
        "an uplifted price is a price no madar page has printed"
    # Nothing to warn about: the manifest states the fact and every row carries it.
    assert not any("configurable" in w for w in table.warnings)


def test_the_declaration_moves_no_price_at_all_only_the_tax_flag():
    """The guard against the bug commit 53b2407 undid, now stated as a rule
    about EVERY shape: declaring the fact must change no figure anywhere.

    The 2026-07-23 uplift multiplied 3,312 rows by 1.15 — 4.23 became 4.86 —
    and the only defence against that is a test that reads the same numbers
    with the switch on and off.
    """
    plain = {r["external_sku"]: r["price"] for r in _shape_rows()[1]}
    declared = {r["external_sku"]: r["price"]
                for r in _shape_rows(shapes_entry(configurable_prices_exclude_tax=True))[1]}

    assert plain == declared, "declaring a tax FACT moved a price"
    assert plain["71102002"] == "4.23"       # the SimpleProduct checked by hand
    assert plain["12512182813"] == "50.4"    # a ConfigurableProduct's variant
    assert plain["115430208"] == "1449"      # a GroupedProduct's member


def test_an_undeclared_configurable_is_still_recorded_but_says_so_once():
    """Undeclared, a row is stored at the source's own vat_mode — never
    converted, never dropped. But madar proved this is the shape where a
    Magento store's two answers diverge, so a run states the assumption once
    rather than letting the next store repeat the 3,312-row mistake in silence.
    """
    table, rows = _shape_rows()
    plywood = [r for r in rows if r["product_name_ar"] == "Tigercore Shuttering Plywood"]
    assert len(plywood) == 2, "an undeclared configurable is recorded, not skipped"
    assert all(r["tax_included"] == "1" for r in plywood), "the source's own vat_mode"
    note = next(w for w in table.warnings if "configurable prices recorded" in w)
    assert "configurable_prices_exclude_tax" in note, \
        "the note must name the declaration that makes these rows truthful"
    assert "12512-TSP" in note


def test_simple_and_grouped_rows_keep_the_storefronts_vat_state():
    """Only the configurable shape is quoted before tax. A simple product's
    figure and a grouped member's both matched the page exactly, so they carry
    tax_included=1 in the very same table."""
    _table, rows = _shape_rows(shapes_entry(configurable_prices_exclude_tax=True))
    simple = next(r for r in rows if r["external_sku"] == "71102002")
    member = next(r for r in rows if r["product_name_ar"] == "الخشب الأحمر السويدي")
    plywood = next(r for r in rows if r["product_name_ar"] == "Tigercore Shuttering Plywood")

    assert simple["tax_included"] == "1"
    assert member["tax_included"] == "1"
    assert plywood["tax_included"] == "0"
    assert len({simple["tax_included"], plywood["tax_included"]}) == 2, \
        "one crawl of one source carries BOTH answers — that is the whole point"


def test_a_grouped_product_whose_members_agree_still_reaches_the_table():
    """The Tameer rebar group: 3 members, all 3,139.50 — the page prints that
    figure three times. The old single row happened to be right here; the fix
    must not lose the product to make a point."""
    _table, rows = _shape_rows()
    rebar = [r for r in rows if r["product_name_ar"] == "حديد تسليح تعمير"]
    assert len(rebar) == 3
    assert {r["price"] for r in rebar} == {"3139.5"}


def test_a_product_whose_price_range_really_is_a_range_is_skipped_out_loud():
    """No BundleProduct exists on madar today (0 of 760). If one appears, its
    price_range is a genuine min..max and its minimum is a "from" figure, so it
    is refused rather than filed as a price."""
    bundled = {"data": {"products": {
        "page_info": {"current_page": 1, "total_pages": 1},
        "items": [{
            "__typename": "BundleProduct", "uid": "QlVOMQ==", "sku": "KIT-1",
            "name": "طقم أدوات", "url_key": "tool-kit", "stock_status": "IN_STOCK",
            "categories": [],
            "price_range": {"minimum_price": {"regular_price": {"value": 120.0},
                                              "final_price": {"value": 120.0}},
                            "maximum_price": {"final_price": {"value": 380.0}}},
        }]}}}

    class _Bundle(_ShapesFetcher):
        def post(self, url, json=None, **kwargs):
            answer = super().post(url, json=json, **kwargs)
            payload = answer.json()
            if ((payload.get("data") or {}).get("products") or {}).get("items"):
                return _StubResponse(bundled)
            return answer

    table = next(iter(MagentoGraphqlConnector(_Bundle()).fetch(shapes_entry())))
    assert table.rows == []
    assert any("price RANGE" in w and "120.0..380.0" in w for w in table.warnings)


def test_a_note_raised_on_a_later_page_is_not_thrown_away():
    """Warnings used to be pinned to page 1, so everything a later page had to
    say was dropped on the floor — a report nobody hears is the silent loss the
    warnings exist to prevent."""

    class _TwoPages(_ShapesFetcher):
        def post(self, url, json=None, **kwargs):
            if (kwargs.get("headers") or {}).get("Store"):
                return super().post(url, json=json, **kwargs)
            if "categoryList" in (json or {}).get("query", ""):
                return super().post(url, json=json, **kwargs)
            self.requests_count += 1
            page = (json or {}).get("variables", {}).get("currentPage", 1)
            shapes = SHAPES["data"]["products"]["items"]
            if page == 1:
                keep = [i for i in shapes if i["__typename"] == "SimpleProduct"]
            elif page == 2:
                keep = [i for i in shapes if i["__typename"] == "ConfigurableProduct"]
            else:
                keep = []
            return _StubResponse({"data": {"products": {
                "items": keep,
                "page_info": {"current_page": page, "total_pages": 2}}}})

    tables = list(MagentoGraphqlConnector(_TwoPages()).fetch(shapes_entry()))
    assert len(tables) == 2
    assert not any("configurable prices recorded" in w for w in tables[0].warnings)
    assert any("configurable prices recorded" in w for w in tables[1].warnings), \
        "page 2 must carry the note page 2 raised"


class _BilingualEnrichedFetcher(_StubFetcher):
    """Both stores answer: the default (Arabic) pass serves the fixture, the
    en_SA pass serves English names AND details, and each store names its
    attributes in its own words — which is what madar actually does."""

    LABELS_AR = {"manufacturer": "المصنع", "origin": "بلد المنشأ",
                 "grade": "تصنيف المواد", "size": "الحجم"}
    LABELS_EN = {"manufacturer": "Manufacturer", "origin": "Country of Origin",
                 "grade": "Material Grade", "size": "Size"}

    def post(self, url, json=None, **kwargs):
        query = (json or {}).get("query", "")
        store = (kwargs.get("headers") or {}).get("Store")
        if "customAttributeMetadataV2" in query:
            labels = self.LABELS_EN if store else self.LABELS_AR
            return _StubResponse({"data": {"customAttributeMetadataV2": {
                "items": [{"code": c, "label": l} for c, l in labels.items()]}}})
        if store:
            page = (json or {}).get("variables", {}).get("currentPage", 1)
            if page != 1:
                return _StubResponse({"data": {"products": {"items": []}}})
            return _StubResponse({"data": {"products": {
                "page_info": {"total_pages": 1},
                "items": [{
                    "uid": "Q0VNMg==",
                    "name": "Riyadh Cement",
                    "description": {"html": "<p>Portland cement for structures.</p>"},
                    "short_description": {"html": "<p>The company provides cement.</p>"},
                    "custom_attributesV2": {"items": [
                        {"code": "manufacturer", "value": "Riyadh Cement Co."},
                        {"code": "grade",
                         "selected_options": [{"label": "A500"}]},
                    ]},
                }]}}})
        return super().post(url, json=json, **kwargs)


def test_the_more_information_labels_are_the_sites_words_in_both_stores():
    """The owner's report, with the site's own tab as evidence: madar prints
    «المصنع», «بلد المنشأ», «الطول (متر)» — and the panel showed manufacturer,
    origin, length_cm. The label existed for every attribute; only the facet
    subset had ever been ASKED for its words (aggregations covers what the
    shop filters by, nothing else). customAttributeMetadataV2 answers for all
    of them, once per store."""
    from scrapex.rowspec import ENRICHMENT

    entry = SourceEntry.model_validate(dict(
        source_key="MADAR", source_name="المدار", base_url="https://www.madar.com",
        family="magento-graphql", currency="SAR", default_region="SA", vat_mode="excl",
        extract=[ExtractSpec(kind=ExtractKind.PRODUCT_PRICES, scope=ExtractScope.CENSUS),
                 ExtractSpec(kind=ExtractKind.ENRICHMENT, scope=ExtractScope.CENSUS)],
    ))
    tables = list(MagentoGraphqlConnector(_BilingualEnrichedFetcher()).fetch(entry))
    view = RowView(ENRICHMENT, tables[-1].header)
    rows = [view.as_dict(r) for r in tables[-1].rows
            if view.as_dict(r)["external_product_id"] == "Q0VNMg=="]
    by_code = {r["attribute_code"]: r for r in rows}

    # The Arabic edition, under the marked code, in the site's Arabic words.
    assert by_code["manufacturer_ar"]["attribute_label"] == "المصنع"
    assert by_code["manufacturer_ar"]["raw_value"] == "اسمنت الرياض"
    assert by_code["manufacturer_ar"]["lang"] == "ar"
    # The English edition, under the unmarked code, from the en_SA pass —
    # value AND label, on pages the names already paid for.
    assert by_code["manufacturer"]["attribute_label"] == "Manufacturer"
    assert by_code["manufacturer"]["raw_value"] == "Riyadh Cement Co."
    assert by_code["manufacturer"]["lang"] == "en"
    # Descriptions pair the same way, in OUR labels, marked per 0041. The
    # fixture's cement publishes a SHORT description only in Arabic, so
    # description_ar is rightly absent — an empty value never mints a row.
    assert by_code["description"]["raw_value"] == "Portland cement for structures."
    assert by_code["description"]["attribute_label"] == "Description"
    assert "description_ar" not in by_code
    assert by_code["short_description_ar"]["attribute_label"] == "Summary (AR)"
    assert by_code["short_description"]["raw_value"] == "The company provides cement."
    # A dropdown the en store answers as selected_options keeps working.
    assert by_code["grade"]["raw_value"] == "A500"
    assert by_code["grade"]["attribute_label"] == "Material Grade"


class _EnglishStoreDownFetcher(_BilingualEnrichedFetcher):
    """Both stores exist; en_SA is unreachable for the length of this run —
    a timeout, a WAF, a deploy. The Arabic pass is untouched, which is exactly
    what makes the failure dangerous: the prices are all there."""

    def post(self, url, json=None, **kwargs):
        if (kwargs.get("headers") or {}).get("Store") == "en_SA":
            raise RuntimeError("en_SA did not answer")
        return super().post(url, json=json, **kwargs)


def _enriched_madar() -> SourceEntry:
    return SourceEntry.model_validate(dict(
        source_key="MADAR", source_name="المدار", base_url="https://www.madar.com",
        family="magento-graphql", currency="SAR", default_region="SA", vat_mode="excl",
        extract=[ExtractSpec(kind=ExtractKind.PRODUCT_PRICES, scope=ExtractScope.CENSUS),
                 ExtractSpec(kind=ExtractKind.ENRICHMENT, scope=ExtractScope.CENSUS)],
    ))


def _cement_price_row(table) -> dict:
    view = RowView(PRODUCT_PRICES, table.header)
    for raw in table.rows:
        row = view.as_dict(raw)
        if row["external_product_id"] == "Q0VNMg==":
            return row
    raise AssertionError("the cement product is missing from the price table")


def test_a_dead_english_store_never_publishes_half_a_brand():
    """The brand is HALF the en_SA store's, and the whole of it is in the price key.

    Publishing the Arabic half alone leaves the key's FIELD SET identical while
    the digest changes — and pricehistory can read that one way only: the price
    moved. Once, into an append-only table, for every offer the source has. So
    a failed English pass suppresses the pair whole: `brand` then drops out of
    the field set, the two keys are not comparable, and the period that opens
    says fields_changed, which is what actually happened.
    """
    from scrapex import pricekey
    from scrapex.normalize import joined_brand

    entry = _enriched_madar()
    healthy = _cement_price_row(
        list(MagentoGraphqlConnector(_BilingualEnrichedFetcher()).fetch(entry))[0])
    degraded_table = list(MagentoGraphqlConnector(_EnglishStoreDownFetcher()).fetch(entry))[0]
    degraded = _cement_price_row(degraded_table)

    # What the source publishes when both stores answer.
    assert healthy["brand_ar"] == "اسمنت الرياض"
    assert healthy["brand"] == "Riyadh Cement Co."
    # And when one does not: nothing, rather than half.
    assert degraded["brand_ar"] == "", "the Arabic half was published alone"
    assert degraded["brand"] == ""

    # The property that makes the suppression worth doing, asserted where it
    # actually decides: the field SET. Same set + different digest is the
    # phantom price change; a different set is a comparison refused.
    def key_of(row: dict):
        return pricekey.build(effective=row["price"], currency=row["currency"],
                              vat=row["tax_included"],
                              brand=joined_brand(row["brand_ar"], row["brand"]))

    assert "brand" in key_of(healthy).fields
    assert "brand" not in key_of(degraded).fields
    assert not pricekey.comparable(key_of(healthy).fields, key_of(degraded).fields), \
        "a degraded round is still being compared to a healthy one as a price"

    # And the run may not report clean: the rows it wrote are knowingly poorer
    # than the source publishes.
    assert degraded_table.defects, "a degraded round produced no defect"
    assert "English store" in degraded_table.defects[0]


def test_a_degraded_fetch_makes_the_run_red_not_merely_noisy():
    """A warning is read by nobody at 2am; errors_count is what S8 alerts on.

    The count is written INSIDE ingest_payloads, so a defect appended by the
    caller afterwards would never reach crawl_run — hence the seam takes it.
    """
    conn: sqlite3.Connection = dbmod.connect(":memory:")
    try:
        dbmod.migrate(conn)
        entry = _enriched_madar()
        table = list(MagentoGraphqlConnector(_EnglishStoreDownFetcher()).fetch(entry))[0]
        result = ingest_payloads(conn, entry, [table.to_payload()],
                                 fetch_defects=table.defects)
        assert result.errors, "the fetch defect never reached the ingest result"
        recorded = conn.execute(
            "SELECT errors_count FROM crawl_run WHERE run_id = ?",
            (result.run_id,)).fetchone()[0]
        assert recorded >= 1, "a run that wrote knowingly degraded rows reported clean"
    finally:
        conn.close()


def test_a_monolingual_source_is_not_treated_as_a_degraded_one():
    """The guard above must not fire where nothing went wrong.

    A source that never asked for enrichment has an empty details map every
    single run — that is its steady state, not a failure. Suppressing the pair
    there would invent the instability the suppression exists to prevent.
    """
    table = next(iter(MagentoGraphqlConnector(_StubFetcher()).fetch(make_entry())))
    assert table.defects == []


def test_a_store_that_declines_to_name_an_attribute_is_reported():
    """420 rows carried a bare code across two "fixed" crawls because nothing
    ever said the shop had declined to name them.

    _attribute_labels only appended a note when the whole request RAISED. A code
    that came back with no label at all was silent, the panel printed the code,
    and it read as a bug nobody had got round to. madar genuinely publishes no
    word for voltage/wattage/cct and 17 others — in either store view — so the
    fix is not to invent one (the owner's rule: the site's text is the record)
    but to make the silence visible.
    """
    from scrapex.connectors.magento import MagentoGraphqlConnector

    class _Fetcher:
        def post(self, url, **kw):
            class _R:
                # The shop answers for one code and says nothing about the other.
                @staticmethod
                def json():
                    return {"data": {"customAttributeMetadataV2": {"items": [
                        {"code": "manufacturer", "label": "Manufacturer"}]}}}
            return _R()

    connector = MagentoGraphqlConnector.__new__(MagentoGraphqlConnector)
    connector._fetcher = _Fetcher()
    notes: list[str] = []
    found = connector._attribute_labels(
        "http://shop/graphql", None, notes, {"manufacturer", "voltage", "wattage"})

    assert found == {"manufacturer": "Manufacturer"}
    assert len(notes) == 1
    assert "voltage" in notes[0] and "wattage" in notes[0]
    assert "manufacturer" not in notes[0], "a code that WAS named must not be reported"
