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
    assert v12["effective_price"] == "112.5"
    assert v12["option_fingerprint"] == "thickness_mm=12"
    assert v12["currency"] == "SAR" and v12["region"] == "SA" and v12["vat_included"] == "0"

    v18 = view.as_dict(table.rows[1])
    assert v18["effective_price"] == "168.78" and v18["regular_price"] == "200.0"  # on sale
    assert v18["sale_price"] == "168.78"

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
        assert row["category_path"] == "مواد البناء > الأخشاب > أخشاب معالجة"
        assert row["category_external_id"] == "Q0FULTQ0"

    simple = view.as_dict(table.rows[2])
    assert simple["category_path"] == "أسمنت"     # one flat filing, one level
    assert simple["category_external_id"] == "Q0FULTc="


def test_classification_lands_on_the_product_and_reaches_the_main_table():
    entry = make_entry()
    table = next(iter(MagentoGraphqlConnector(_StubFetcher()).fetch(entry)))
    conn: sqlite3.Connection = dbmod.connect(":memory:")
    try:
        dbmod.migrate(conn)
        ingest_payloads(conn, entry, [table.to_payload()])

        stored = dict(conn.execute(
            "SELECT external_product_id, category_path FROM source_product").fetchall())
        assert stored["NDY3Mg=="] == "مواد البناء > الأخشاب > أخشاب معالجة"

        from scrapex.reports import table_payload
        grid = table_payload(conn, "MADAR")
        keys = {c["key"] for c in grid["columns"]}
        # Three levels published -> exactly L1..L3 offered, never an empty L4.
        assert {"category", "category_l1", "category_l2", "category_l3"} <= keys
        assert "category_l4" not in keys
        plywood = next(r for r in grid["rows"]
                       if r["product_name"].startswith("Fire Retardant"))
        assert plywood["category"] == "مواد البناء > الأخشاب > أخشاب معالجة"
        assert plywood["category_l1"] == "مواد البناء"
        assert plywood["category_l2"] == "الأخشاب"
        assert plywood["category_l3"] == "أخشاب معالجة"
        cement = next(r for r in grid["rows"] if r["category"] == "أسمنت")
        assert cement["category_l1"] == "أسمنت" and cement["category_l2"] == ""
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
            "SELECT category_path FROM source_product WHERE source_name LIKE '%Cement%' "
            "OR external_product_id = 'Q0VNQg=='").fetchone()[0]
        assert path == "مواد البناء > مواد لاصقة"
        event = conn.execute(
            "SELECT previous_value, new_value FROM change_event "
            "WHERE field_key = 'category_path'").fetchone()
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
    assert plywood["category_path"] == "المعادن والحديد الإنشائي > حديد التسليح والشبك"
    assert plywood["category_external_id"] == "NA=="
    cement = view.as_dict(table.rows[2])
    assert cement["category_path"] == "مواد البناء ولوازم الموقع > الأسمنت والجبس"


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
    assert v12["option_label"] == "السماكة (مم): 12"


def test_the_stated_basis_rides_the_price_and_a_piece_mass_does_not():
    """Riyadh-cement shape: weight 50 AND "50كجم" in the name agree — the
    price is per 50 kg, from the source's own statement. The plywood's 6.72
    is the PIECE's mass with no stated quantity: inventing "per 6.72 kg"
    is exactly the guess the rule refuses."""
    table = next(iter(MagentoGraphqlConnector(_StubFetcher()).fetch(make_entry())))
    view = RowView(PRODUCT_PRICES, table.header)

    cement = view.as_dict(table.rows[3])
    assert cement["unit"] == "kg" and cement["basis_quantity"] == "50"
    assert cement["option_label"] == "نوع الأسمنت: اسمنت ابيض"

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

    v12 = view.as_dict(table.rows[0])
    assert v12["product_name_en"] == "Fire Retardant Plywood - 12mm"
    cement = view.as_dict(table.rows[3])
    assert cement["product_name_en"] == "White Cement - 50kg"

    conn: sqlite3.Connection = dbmod.connect(":memory:")
    try:
        dbmod.migrate(conn)
        table2 = next(iter(MagentoGraphqlConnector(_BilingualFetcher()).fetch(make_entry())))
        ingest_payloads(conn, make_entry(), [table2.to_payload()])
        stored = conn.execute(
            "SELECT source_name_en FROM source_product "
            "WHERE external_product_id = 'Q0VNMg=='").fetchone()[0]
        # The product is named from the first row seen — the variant's row —
        # exactly how the primary (Arabic) name behaves. Consistency, not loss.
        assert stored == "White Cement - 50kg"

        from scrapex.reports import table_payload
        grid = table_payload(conn, "MADAR")
        assert "product_name_en" in {c["key"] for c in grid["columns"]},             "a bilingual source must offer the Record (EN) column"
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
        assert "product_name_en" not in {c["key"] for c in grid["columns"]}
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
    assert by_code["manufacturer"]["raw_value"] == "اسمنت الرياض"
    assert by_code["grade"]["raw_value"] == "A500"          # dropdown -> label
    assert by_code["size"]["raw_value"] == "50 Kg"
    assert by_code["manufacturer"]["attribute_group"] == "More information"
    assert "توفر شركة" in by_code["short_description"]["raw_value"]
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
    ctx = {"base": "https://x", "currency": "SAR", "vat": "0", "region": "SA",
           "paths": {"P1": ("التخفيضات والعروض الحصرية الكبرى للمقاولين", "PROMO")}}

    rows = MagentoGraphqlConnector._product_rows(builder, product, ctx)
    row = RowView(PRODUCT_PRICES, builder.header).as_dict(rows[0])
    assert row["category_path"] == "مواد > معادن > حديد"
    assert row["category_external_id"] == "C3"
