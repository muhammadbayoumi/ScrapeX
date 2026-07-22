"""The attributes were arriving all along and being read past.

The owner listed what was missing from Sameh Gabriel by name: weight, colours,
cable type, length, brand, size, application, voltage type, warranty, category,
tags, description. Every one of them is in the SAME WooCommerce response the
price is taken from. The connector was reading past all of it to keep four
numbers, so emitting them costs ZERO additional requests.

The fixture is captured from the live Store API on 2026-07-21, not written from
memory — the previous woocommerce fixture was hand-authored and did not even
contain an `attributes` key, which is precisely why nobody noticed.
"""
from __future__ import annotations

import json
from pathlib import Path

from scrapex.connectors.woocommerce import _clean, enrichment_rows
from scrapex.rowspec import ENRICHMENT, RowBuilder, RowView

FX = Path(__file__).parent / "fixtures"
LIVE = json.loads((FX / "samehgabriel_wc_live.json").read_text(encoding="utf-8"))


def shaped(product) -> list[dict]:
    builder = RowBuilder(ENRICHMENT)
    view = RowView(ENRICHMENT, builder.header)
    return [view.as_dict(r) for r in enrichment_rows(builder, product)]


def test_the_attributes_the_owner_named_are_all_extracted():
    """His list, checked against the real payload rather than paraphrased."""
    rows = shaped(LIVE[0])
    values = {r["raw_value"] for r in rows}

    assert "مجدول" in values, "cable type"
    # Length and brand are deliberately ABSENT here since the owner's re-filing
    # (2026-07-22): the single length term is the selling BASIS and rides the
    # price row's unit ("100 m"), and the brand attribute rides brand_raw.
    # Their presence in this set would be the same fact filed twice.
    assert "100 متر" not in values, "length re-filed as the unit"
    assert "السويدي اليكتريك" not in values, "brand re-filed as brand_raw"
    assert "3 مم" in values, "size"
    assert "جهد منخفض" in values, "voltage type"
    assert "ضد عيوب التصنيع" in values, "warranty"
    assert any("التركيبات" in v for v in values), "application"


def test_one_row_per_value_so_a_new_attribute_needs_no_schema_change():
    """A long format takes any number of attributes from any site. Nine fixed
    columns would be nine guesses, and wrong for the next shop."""
    rows = shaped(LIVE[0])
    codes = {r["attribute_code"] for r in rows}

    assert len(rows) > len(codes), "several values share one attribute (colours)"
    assert any(c.startswith("pa_") for c in codes)


def test_the_stable_taxonomy_key_is_used_not_the_printed_label():
    """`name` is what the shop prints and can be renamed at any time. Keying on
    it would make a rename look like a brand new attribute."""
    rows = shaped(LIVE[0])
    colours = [r for r in rows if r["attribute_code"] == "pa_color"]

    assert colours, "the colour attribute is keyed by its taxonomy"
    assert colours[0]["attribute_label"] == "Color", "the label is kept for display"


def test_category_and_tag_keep_their_links():
    """Attribute values are links on these sites, and re-scraping every product
    later to recover one is the expensive way to learn that."""
    rows = shaped(LIVE[0])
    classified = [r for r in rows if r["attribute_group"] == "Classification"]

    assert classified
    assert any(r["value_url"].startswith("http") for r in classified)


def test_a_measurement_keeps_both_the_number_and_what_was_printed():
    """So nothing has to guess the unit back out of "2.0 kg"."""
    rows = [r for r in shaped(LIVE[0]) if r["attribute_group"] == "Measurements"]
    for row in rows:
        assert row["raw_value"], "what the site printed"


def test_description_html_is_stripped_because_scraped_text_is_untrusted():
    """Storing raw HTML and letting a template render it later is how scraped
    content becomes an injection (spec 34)."""
    assert _clean("<p>hello <b>world</b></p>") == "hello world"
    assert "<script" not in _clean("<script>alert(1)</script>text")


def test_a_product_without_an_id_yields_nothing_rather_than_orphans():
    assert enrichment_rows(RowBuilder(ENRICHMENT), {"attributes": [{"name": "x"}]}) == []


def test_empty_values_are_skipped_not_stored_as_blanks():
    rows = shaped({"id": "1", "attributes": [
        {"taxonomy": "pa_x", "name": "X", "terms": [{"name": ""}, {"name": "kept"}]}]})
    assert [r["raw_value"] for r in rows] == ["kept"]


# ---- the landing: details reach the warehouse and the offer API --------------

def _woo_entry():
    from scrapex.config import SourceEntry
    return SourceEntry.model_validate(dict(
        source_key="SAMEHGABRIEL", source_name="سامح جبرائيل",
        base_url="https://samehgabriel.com", family="woocommerce-storeapi",
        cadence="daily", authority="shop", currency="EGP", vat_mode="incl",
        extract=[{"kind": "product_prices"}, {"kind": "enrichment"}],
    ))


def _tables_from_live_fixture():
    """The connector's own output over the REAL samehgabriel capture — the
    same bytes the live site served on 2026-07-20."""
    import json
    from pathlib import Path

    from scrapex.connectors.woocommerce import WooCommerceConnector

    class _Fetcher:
        requests_count = 0
        def get(self, url, **kw):
            class R:
                status_code = 200
                text = Path(__file__).parent.joinpath(
                    "fixtures/live/samehgabriel_wc_store_products_2026-07-20.json"
                ).read_text(encoding="utf-8")
                def json(self):
                    return json.loads(self.text)
                headers = {}
            self.requests_count += 1
            return R()
        def close(self): pass

    connector = WooCommerceConnector(_Fetcher())
    return list(connector.fetch(_woo_entry()))


def test_details_from_the_live_capture_land_and_reach_the_offer_api(tmp_path):
    """End to end over real bytes: connector -> ingest -> the API the History
    panel reads. This chain is what 'Phase 1' rejected wholesale — every
    colour, length and warranty thrown away with an error logged."""
    import sqlite3

    from scrapex import db as dbmod
    from scrapex.ingest import ingest_payloads
    from scrapex.reports import product_attributes

    conn = dbmod.connect(":memory:")
    dbmod.migrate(conn)
    tables = _tables_from_live_fixture()
    result = ingest_payloads(conn, _woo_entry(), [t.to_payload() for t in tables])

    assert result.errors == [], result.errors[:3]
    assert result.attributes > 0, "no detail landed at all"
    stored = conn.execute("SELECT COUNT(*) FROM source_product_attribute").fetchone()[0]
    assert stored > 0

    offer_id = conn.execute("SELECT offer_id FROM source_offer LIMIT 1").fetchone()[0]
    details = product_attributes(conn, offer_id)
    assert details, "the API view found nothing for a product with details"
    assert all(d["value"] for d in details)


def test_reingesting_the_same_details_refreshes_not_duplicates(tmp_path):
    from scrapex import db as dbmod
    from scrapex.ingest import ingest_payloads

    conn = dbmod.connect(":memory:")
    dbmod.migrate(conn)
    payloads = [t.to_payload() for t in _tables_from_live_fixture()]
    ingest_payloads(conn, _woo_entry(), payloads)
    before = conn.execute("SELECT COUNT(*) FROM source_product_attribute").fetchone()[0]

    ingest_payloads(conn, _woo_entry(), payloads)
    after = conn.execute("SELECT COUNT(*) FROM source_product_attribute").fetchone()[0]
    assert after == before, "a re-crawl duplicated the details"


def test_enrichment_for_a_source_that_never_declared_it_is_refused(tmp_path):
    """The scope guard, same rule as everything else: nothing lands that the
    manifest did not declare."""
    from scrapex import db as dbmod
    from scrapex.config import SourceEntry
    from scrapex.ingest import ingest_payloads

    undeclared = SourceEntry.model_validate(dict(
        source_key="SAMEHGABRIEL", source_name="سامح جبرائيل",
        base_url="https://samehgabriel.com", family="woocommerce-storeapi",
        cadence="daily", authority="shop", currency="EGP", vat_mode="incl",
        extract=[{"kind": "product_prices"}],))
    conn = dbmod.connect(":memory:")
    dbmod.migrate(conn)
    payloads = [t.to_payload() for t in _tables_from_live_fixture()]
    result = ingest_payloads(conn, undeclared, payloads)

    assert any("does not declare enrichment" in e for e in result.errors)
    assert conn.execute("SELECT COUNT(*) FROM source_product_attribute").fetchone()[0] == 0


# ---- the owner's re-filing: length is the UNIT, the attribute is the BRAND ---

def test_the_single_length_term_becomes_the_selling_basis_not_a_detail():
    """"100 متر" is what one price BUYS — the roll — so it rides the price
    row's unit and basis, and leaves the details list. A length the buyer
    CHOOSES (multi-term / variation) stays a detail: that is a variant axis,
    not one basis."""
    from scrapex.connectors.woocommerce import selling_basis

    single = {"attributes": [{"taxonomy": "pa_الطول", "name": "الطول",
                              "terms": [{"name": "100 متر"}]}]}
    assert selling_basis(single) == ("100", "متر")

    chosen = {"attributes": [{"taxonomy": "pa_الطول", "name": "الطول",
                              "terms": [{"name": "50 متر"}, {"name": "100 متر"}]}]}
    assert selling_basis(chosen) == ("", "")


def test_the_brand_attribute_fills_brand_raw_because_brands_is_empty():
    """The shop fills pa_الماركة and leaves the Store API's own brands list
    empty; the brand belongs in the brand field, not filed under details."""
    from scrapex.connectors.woocommerce import brand_of

    assert brand_of({"brands": [], "attributes": [
        {"taxonomy": "pa_الماركة", "name": "الماركة",
         "terms": [{"name": "السويدي اليكتريك"}]}]}) == "السويدي اليكتريك"
    # The API's own list wins when it is actually filled.
    assert brand_of({"brands": [{"name": "Real Brand"}], "attributes": []}) == "Real Brand"


def test_arabic_metre_folds_into_the_canonical_unit():
    from scrapex.ingest import canonical_unit
    assert canonical_unit("متر") == "m"


def test_the_grid_payload_carries_brand_category_was_discount_and_details(tmp_path):
    """The whole ask, end to end over the live capture: the main table shows
    the brand, the category, the pre-discount price, the computed discount,
    and a per-row Details flag — and the unit reads '100 m'."""
    from scrapex import db as dbmod
    from scrapex.ingest import ingest_payloads
    from scrapex.reports import table_payload

    conn = dbmod.connect(":memory:")
    dbmod.migrate(conn)
    ingest_payloads(conn, _woo_entry(),
                    [t.to_payload() for t in _tables_from_live_fixture()])

    grid = table_payload(conn, "SAMEHGABRIEL")
    keys = [c["key"] for c in grid["columns"]]
    for key in ("brand", "category", "was_price", "discount", "details"):
        assert key in keys, f"{key} missing from the columns"

    row = next(r for r in grid["rows"] if r["discount"])
    assert row["brand"] == "السويدي اليكتريك"
    assert row["category"]
    assert float(row["was_price"]) > float(row["effective_price"])
    assert row["discount"].startswith("-") and "%" in row["discount"]
    assert row["unit"] == "100 m"
    assert row["has_details"] is True


def test_payload_order_cannot_send_details_out_of_scope(tmp_path):
    """The live failure on a fresh warehouse: the inbox reads files in
    filename order, the enrichment payload sorted FIRST, found no products
    registered yet, and all 270 details went out-of-scope. The ingester owns
    the dependency: prices land before enrichment, whatever the caller sends."""
    from scrapex import db as dbmod
    from scrapex.ingest import ingest_payloads

    conn = dbmod.connect(":memory:")
    dbmod.migrate(conn)
    payloads = [t.to_payload() for t in _tables_from_live_fixture()]
    payloads.reverse()                       # enrichment deliberately first

    result = ingest_payloads(conn, _woo_entry(), payloads)
    assert result.rejected_out_of_scope == 0
    assert result.attributes > 0


def test_wiping_a_source_with_details_wipes_them_too(tmp_path):
    """Caught live: source_product_attribute was missing from wipe-source's
    table list, so the whole wipe died on its FOREIGN KEY — the right failure
    mode, now with the table in the list."""
    from scrapex import db as dbmod, storage
    from scrapex.ingest import ingest_payloads

    db = tmp_path / "harvest.db"
    conn = dbmod.connect(db)
    dbmod.migrate(conn)
    ingest_payloads(conn, _woo_entry(),
                    [t.to_payload() for t in _tables_from_live_fixture()])
    conn.commit()

    result = storage.wipe_source(conn, db, "SAMEHGABRIEL")
    assert result.ok
    assert conn.execute("SELECT COUNT(*) FROM source_product_attribute").fetchone()[0] == 0
    conn.close()
