"""T2: magento-graphql connector against a recorded madar-shaped GraphQL response."""
from __future__ import annotations

import json
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
    """Serves the fixture on page 1, an empty page after (ends pagination)."""
    def __init__(self): self.requests_count = 0
    def post(self, url, json=None, **kwargs):
        self.requests_count += 1
        page = (json or {}).get("variables", {}).get("currentPage", 1)
        return _StubResponse(FIXTURE if page == 1 else {"data": {"products": {"items": []}}})
    def close(self): pass


def make_entry() -> SourceEntry:
    return SourceEntry.model_validate(dict(
        source_key="MADAR", source_name="المدار", base_url="https://www.madar.com",
        family="magento-graphql", currency="SAR", default_region="SA", vat_mode="excl",
        extract=[ExtractSpec(kind=ExtractKind.PRODUCT_PRICES, scope=ExtractScope.CENSUS)],
    ))


def test_magento_maps_variants_and_simple():
    table = next(iter(MagentoGraphqlConnector(_StubFetcher()).fetch(make_entry())))
    assert table.header == list(PRODUCT_PRICES.columns)
    assert len(table.rows) == 3  # 2 variants + 1 simple product

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
    assert result.observations == 3 and result.products == 2 and result.variants == 3
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
        moved["data"]["products"]["items"][-1]["categories"] = [
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
