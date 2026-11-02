"""A product a complete crawl no longer finds is marked, and only then (#1841).

His ruling of 2026-10-31: it stays in the table, marked and filterable, and it
stays in the Sheet with the same mark («تبقى فى الشيت بنفس العلامة»). Its history
stays, and it comes back by itself.

WHY THE MARK SAYS "NO LONGER LISTED" AND NOT "GONE FROM THE SITE". Of three unseen
madar products opened on 2026-10-31, one answered 404 and two redirected to a new
parent product that holds them as options. The crawl knows the record is not in the
listing. It cannot know why, and a state must not claim a cause it cannot know.

THE GATE IS THE POINT, as in contractors.mark_departures: a connector that did not
prove it walked the whole listing marks nothing, and a product it met and refused
is not gone. Masdar's last run said "905 product(s) publish no price at all".
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

from scrapex import capture as capmod
from scrapex import changes, localinbox, reports
from scrapex import db as dbmod
from scrapex.capture import capture_source
from scrapex.config import MANIFEST_FILE, load_manifest
from scrapex.connectors.base import ScrapedTable
from scrapex.connectors.custom_json import CustomJsonConnector
from scrapex.connectors.magento import GraphqlRefused, MagentoGraphqlConnector
from scrapex.ingest import (
    canary_breach,
    ingest_payloads,
    mark_unlisted_products,
    previous_rows_seen,
)
from scrapex.jobs import create_job, get_job
from scrapex.publish import workbook_tables
from scrapex.rowspec import PRODUCT_PRICES
from scrapex.vocab import ExtractKind, ExtractScope
from tests.test_ingest import make_entry, make_payload, one_row


def _row(product: str, **over) -> list[str]:
    return one_row(external_product_id=product, external_variant_id=f"v{product}",
                   external_sku=f"SKU{product}", **over)


class _Fetcher:
    requests_count = 0
    def close(self): pass


class _Connector:
    """A crawl that lists these products and says what it can prove."""

    def __init__(self, products, *, proven=True, refused=(), error=None):
        self.products, self.census_proven = products, proven
        self.refused, self.error = list(refused), error
        self.skip_tokens: set[str] = set()

    def fetch(self, source):
        if self.error:
            raise self.error
        rows = [_row(p) for p in self.products]
        header = make_payload([one_row()]).header
        yield ScrapedTable(source.source_key, PRODUCT_PRICES.kind, "https://elsewedyshop.com",
                           header, rows, refused_products=self.refused)


def _crawl(conn, entry, connector, **kwargs):
    original = capmod.build_connector
    capmod.build_connector = lambda e, rules, crawl=None: (connector, _Fetcher())
    try:
        return capture_source(conn, entry, **kwargs)
    finally:
        capmod.build_connector = original


@pytest.fixture()
def seeded(tmp_path: Path):
    entry = make_entry()
    conn = dbmod.connect(tmp_path / "w.db")
    dbmod.migrate(conn)
    ingest_payloads(conn, entry, [make_payload([_row("1"), _row("2"), _row("3"), _row("4")])])
    yield entry, conn
    conn.close()


def _status(conn) -> dict[str, str]:
    return dict(conn.execute(
        "SELECT external_product_id, status FROM source_product"))


def test_a_proven_census_marks_what_it_did_not_find(seeded):
    entry, conn = seeded
    result = _crawl(conn, entry, _Connector(["1", "2", "3"]))
    assert _status(conn) == {"1": "active", "2": "active", "3": "active", "4": "vanished"}
    assert any("no longer listed" in n for n in result.ingest.notices), result.ingest.notices


def test_the_mark_is_a_recorded_change(seeded):
    entry, conn = seeded
    _crawl(conn, entry, _Connector(["1", "2", "3"]))
    assert [tuple(r) for r in conn.execute(
        "SELECT change_type, field_key, previous_value, new_value FROM change_event "
        "WHERE change_type = 'removed'")] == [("removed", "status", "active", "vanished")]


def test_a_crawl_that_proves_nothing_marks_nothing(seeded):
    """Every connector but the two that declare a proof, today."""
    entry, conn = seeded
    _crawl(conn, entry, _Connector(["1", "2", "3"], proven=False))
    assert set(_status(conn).values()) == {"active"}


def test_a_connector_with_no_proof_attribute_marks_nothing(seeded):
    class _Silent(_Connector):
        def __init__(self, products):
            super().__init__(products)
            del self.census_proven
    entry, conn = seeded
    _crawl(conn, entry, _Silent(["1", "2", "3"]))
    assert set(_status(conn).values()) == {"active"}


def test_a_product_the_connector_refused_is_not_gone(seeded):
    """It met the product and would not store it: still on the site."""
    entry, conn = seeded
    _crawl(conn, entry, _Connector(["1", "2", "3"], refused=["4"]))
    assert _status(conn)["4"] == "active"


def test_a_targeted_source_marks_nothing(tmp_path):
    from scrapex.config import ExtractSpec
    entry = make_entry(extract=[ExtractSpec(kind=ExtractKind.PRODUCT_PRICES,
                                            scope=ExtractScope.TARGETED)])
    census = make_entry()
    conn = dbmod.connect(tmp_path / "t.db")
    dbmod.migrate(conn)
    try:
        ingest_payloads(conn, census, [make_payload([_row("1"), _row("2"), _row("3")])])
        _crawl(conn, entry, _Connector(["1", "2"]))
        assert set(_status(conn).values()) == {"active"}
    finally:
        conn.close()


def test_a_run_with_errors_marks_nothing(seeded, monkeypatch):
    """A partial run says what it holds is incomplete, so absence proves nothing."""
    entry, conn = seeded
    connector = _Connector(["1", "2", "3"])

    def with_defect(source):
        for table in _Connector.fetch(connector, source):
            table.defects = ["the English store failed"]
            yield table

    connector.fetch = with_defect
    _crawl(conn, entry, connector)
    assert set(_status(conn).values()) == {"active"}


def test_a_listing_that_lost_too_much_is_refused_and_said(tmp_path):
    """A site redesign must not mark a catalogue gone. MADAR and SIKA both declare
    max_drop_pct 50, the bound the volume canary already reads."""
    entry = make_entry(max_drop_pct=50)
    conn = dbmod.connect(tmp_path / "d.db")
    dbmod.migrate(conn)
    try:
        ingest_payloads(conn, entry, [make_payload([_row(str(n)) for n in range(1, 11)])])
        result = _crawl(conn, entry, _Connector(["1", "2", "3", "4"]))
        assert set(_status(conn).values()) == {"active"}
        assert any("not marked" in n and "6" in n for n in result.ingest.notices), result.ingest.notices
    finally:
        conn.close()


def test_exactly_at_the_bound_is_marked(tmp_path):
    entry = make_entry(max_drop_pct=50)
    conn = dbmod.connect(tmp_path / "e.db")
    dbmod.migrate(conn)
    try:
        ingest_payloads(conn, entry, [make_payload([_row(str(n)) for n in range(1, 5)])])
        _crawl(conn, entry, _Connector(["1", "2"]))
        assert sorted(_status(conn).values()) == ["active", "active", "vanished", "vanished"]
    finally:
        conn.close()


def test_a_listed_product_comes_back_by_itself(seeded):
    entry, conn = seeded
    _crawl(conn, entry, _Connector(["1", "2", "3"]))
    assert _status(conn)["4"] == "vanished"

    _crawl(conn, entry, _Connector(["1", "2", "3", "4"]))

    assert _status(conn)["4"] == "active"
    assert conn.execute("SELECT COUNT(*) FROM change_event WHERE change_type = 'returned'"
                        ).fetchone()[0] == 1


# ---- what he sees ------------------------------------------------------------

def test_the_table_keeps_the_row_and_says_so(seeded):
    entry, conn = seeded
    _crawl(conn, entry, _Connector(["1", "2", "3"]))

    rows = {r["sku"]: r for r in reports.table_payload(conn, entry.source_key)["rows"]}

    assert rows["SKU4"]["availability"] == "no_longer_listed"
    assert rows["SKU1"]["availability"] == "in_stock"
    assert rows["SKU4"]["price"] == 1200.0, "its last price is still shown beside the mark"


def test_the_browse_page_says_the_same(seeded):
    entry, conn = seeded
    _crawl(conn, entry, _Connector(["1", "2", "3"]))

    rows = {r["sku"]: r for r in reports.browse_observations(conn, entry.source_key).rows}

    assert rows["SKU4"]["availability"] == "no_longer_listed"
    assert rows["SKU1"]["availability"] == "in_stock"


def test_the_browse_filter_finds_the_marked_rows(seeded):
    entry, conn = seeded
    _crawl(conn, entry, _Connector(["1", "2", "3"]))

    page = reports.browse_observations(conn, entry.source_key, availability="no_longer_listed")
    assert [r["sku"] for r in page.rows] == ["SKU4"]

    page = reports.browse_observations(conn, entry.source_key, availability="in_stock")
    assert sorted(r["sku"] for r in page.rows) == ["SKU1", "SKU2", "SKU3"]


def test_the_sheet_keeps_it_with_the_same_mark(seeded):
    """His ruling: no product leaves the Sheet. The mark rides the availability
    column the Sheet already has, so the header does not move."""
    entry, conn = seeded
    _crawl(conn, entry, _Connector(["1", "2", "3"]))

    header, rows = reports.export_source_table(conn, entry.source_key)[:2]

    cells = {row[header.index("sku")]: row[header.index("availability")] for row in rows}
    assert cells == {"SKU1": "in_stock", "SKU2": "in_stock", "SKU3": "in_stock",
                     "SKU4": "no_longer_listed"}


def test_the_publish_path_carries_the_mark(seeded):
    """workbook_tables is what the Sheet, the .xlsx and the funnel all write."""
    entry, conn = seeded
    _crawl(conn, entry, _Connector(["1", "2", "3"]))

    name, header, rows = workbook_tables(conn, entry.source_key)[0]

    assert name == entry.source_key
    cells = {row[header.index("sku")]: row[header.index("availability")] for row in rows}
    assert cells["SKU4"] == "no_longer_listed" and cells["SKU1"] == "in_stock"


def test_its_history_stays(seeded):
    entry, conn = seeded
    before = conn.execute("SELECT COUNT(*) FROM price_observation").fetchone()[0]
    _crawl(conn, entry, _Connector(["1", "2", "3"]))
    assert conn.execute("SELECT COUNT(*) FROM price_observation").fetchone()[0] >= before
    assert conn.execute(
        "SELECT COUNT(*) FROM price_observation po JOIN source_offer so ON so.offer_id=po.offer_id "
        "JOIN source_variant sv ON sv.source_variant_id=so.source_variant_id "
        "WHERE sv.external_sku = 'SKU4'").fetchone()[0] == 1


# ---- the two connectors that can prove it --------------------------------------

class _MagentoResponse:
    def __init__(self, payload): self._payload = payload
    def json(self): return self._payload


def _simple(uid, price=100.0):
    # uid and sku differ, as on the real store: MADAR's ids are base64 uids, and a refusal
    # has to name the one the row is filed under.
    return {"__typename": "SimpleProduct", "uid": uid, "sku": f"SKU-{uid}", "url_key": uid,
            "name": uid, "stock_status": "IN_STOCK", "categories": [], "weight": 1,
            "is_qty_decimal": False, "min_sale_qty": 1, "qty_increments": 1,
            "only_x_left_in_stock": None,
            "price_range": {"minimum_price": {"regular_price": {"value": price},
                                              "final_price": {"value": price}},
                            "maximum_price": {"final_price": {"value": price}}}}


def _ranged(uid):
    product = _simple(uid, 50.0)
    product["price_range"]["maximum_price"]["final_price"]["value"] = 80.0
    return product


class _MagentoFetcher:
    def __init__(self, pages):
        self.pages = pages

    def post(self, url, json=None, **kwargs):
        query = (json or {}).get("query", "")
        page = (json or {}).get("variables", {}).get("currentPage", 1)
        if "storeConfig" in query:
            return _MagentoResponse({"data": {"storeConfig": {"weight_unit": "kgs"}}})
        if "categoryList" in query:
            return _MagentoResponse({"data": {"categoryList": [{"children": []}]}})
        none = {"data": {"products": {"items": [], "page_info": {"current_page": 1, "total_pages": 1}}}}
        if (kwargs.get("headers") or {}).get("Store") or "category_uid" in query:
            return _MagentoResponse(none)
        items = self.pages[page - 1] if page <= len(self.pages) else []
        return _MagentoResponse({"data": {"products": {
            "items": items, "page_info": {"current_page": page, "total_pages": len(self.pages)}}}})

    def close(self): pass


def _magento_entry():
    return make_entry(source_key="MADAR", family="magento-graphql", currency="SAR",
                      default_region="SA", vat_mode="incl", base_url="https://www.madar.com")


def test_magento_proves_a_walk_to_its_last_page():
    connector = MagentoGraphqlConnector(_MagentoFetcher([[_simple("A")], [_simple("B")]]))
    assert connector.census_proven is False, "nothing is proved before the walk"
    list(connector.fetch(_magento_entry()))
    assert connector.census_proven is True


def test_magento_proves_nothing_when_a_page_comes_back_empty_early():
    """total_pages says 2 and page 2 is empty: the listing ended short of its word."""
    connector = MagentoGraphqlConnector(_MagentoFetcher([[_simple("A")], []]))
    list(connector.fetch(_magento_entry()))
    assert connector.census_proven is False


def test_magento_names_the_product_it_refused():
    connector = MagentoGraphqlConnector(_MagentoFetcher([[_simple("A"), _ranged("R")]]))
    tables = list(connector.fetch(_magento_entry()))
    assert [p for t in tables for p in t.refused_products] == ["R"]


class _JsonResponse:
    def __init__(self, payload): self._payload = payload
    def json(self): return self._payload


class _JsonFetcher:
    def __init__(self, pages, total):
        self.pages, self.total = pages, total

    def get(self, url, **kwargs):
        page = int(url.rsplit("page=", 1)[1]) if "page=" in url else 1
        return _JsonResponse({"success": True, "data": self.pages[page - 1], "pagination": {
            "total": self.total, "page": page, "limit": 12, "totalPages": len(self.pages)}})

    def close(self): pass


def _sika_entry():
    return make_entry(source_key="SIKAEGSHOP", family="custom-json-api", currency="EGP",
                      default_region="EG", vat_mode="excl", base_url="https://www.sikaegshop.com")


def _sika(pid, price=10):
    return {"product_id": pid, "product_enname": f"P{pid}", "product_arname": f"م{pid}",
            "price": price, "sale_price": None, "specail_price": None, "stock_quantity": 5,
            "weight": 1, "is_active": True}


def test_the_json_api_proves_a_walk_that_met_its_stated_total():
    connector = CustomJsonConnector(_JsonFetcher([[_sika(1)], [_sika(2)]], total=2))
    list(connector.fetch(_sika_entry()))
    assert connector.census_proven is True


def test_the_json_api_proves_nothing_when_the_count_falls_short():
    """The API said 90 and handed back 89: one may have been missed mid-crawl."""
    connector = CustomJsonConnector(_JsonFetcher([[_sika(1)], [_sika(2)]], total=3))
    list(connector.fetch(_sika_entry()))
    assert connector.census_proven is False


def test_the_json_api_names_the_product_it_refused():
    connector = CustomJsonConnector(_JsonFetcher([[_sika(1), _sika(2, price=0)]], total=2))
    tables = list(connector.fetch(_sika_entry()))
    assert [p for t in tables for p in t.refused_products] == ["2"]
    assert connector.census_proven is True


def test_a_resumed_crawl_marks_nothing(seeded):
    """What the paused attempt refused went with it, so absence proves nothing."""
    entry, conn = seeded
    _crawl(conn, entry, _Connector(["1", "2", "3"]), resume=True)
    assert set(_status(conn).values()) == {"active"}


def test_a_history_backfill_marks_nothing(seeded):
    """It asks for past prices, not for what the listing holds today."""
    entry, conn = seeded
    connector = _Connector(["1", "2", "3"])
    connector._history = False
    _crawl(conn, entry, connector, history=True)
    assert set(_status(conn).values()) == {"active"}


def test_the_column_filter_finds_the_marked_rows(seeded):
    entry, conn = seeded
    _crawl(conn, entry, _Connector(["1", "2", "3"]))
    page = reports.browse_observations(conn, entry.source_key, column_filters={
        "availability": ("is", "no_longer_listed")})
    assert [r["sku"] for r in page.rows] == ["SKU4"]


def test_the_column_filter_offers_the_state(seeded):
    """What the panel's filter is built from, and only once a row carries the mark."""
    entry, conn = seeded
    assert "no_longer_listed" not in reports.facet_options(conn, entry.source_key, "availability")

    _crawl(conn, entry, _Connector(["1", "2", "3"]))

    assert "no_longer_listed" in reports.facet_options(conn, entry.source_key, "availability")


def test_the_schema_page_says_where_the_mark_comes_from():
    assert "no_longer_listed" in reports.column_origin("availability")


def test_a_census_source_whose_proof_failed_says_so(seeded):
    """A crawl that silently marked nothing reads like one that found nothing gone."""
    entry, conn = seeded
    result = _crawl(conn, entry, _Connector(["1", "2", "3"], proven=False))
    assert any("did not prove the listing complete" in n for n in result.ingest.notices)
    assert set(_status(conn).values()) == {"active"}


def test_a_family_that_declares_no_proof_stays_quiet(seeded):
    class _Silent(_Connector):
        def __init__(self, products):
            super().__init__(products)
            del self.census_proven
    entry, conn = seeded
    result = _crawl(conn, entry, _Silent(["1", "2", "3"]))
    assert not any("prove" in n for n in result.ingest.notices)


def _many(product, variants):
    return [one_row(external_product_id=product, external_variant_id=f"v{product}-{v}",
                    external_sku=f"S{product}-{v}", option_fingerprint=f"f{v}")
            for v in range(variants)]


def test_a_run_the_canary_fails_has_marked_nothing(tmp_path):
    """jobs.py fails the run on a volume breach after capture returns, so the marks would be
    written on a run about to read as failed. The bound counts products and the canary rows."""
    entry = make_entry(max_drop_pct=50)
    conn = dbmod.connect(tmp_path / "c.db")
    dbmod.migrate(conn)
    try:
        first = [r for n in range(1, 7) for r in _many(str(n), 1)]
        first += [r for n in range(7, 11) for r in _many(str(n), 5)]
        ingest_payloads(conn, entry, [make_payload(first)])
        previous = previous_rows_seen(conn, entry.source_key)

        class _Thin(_Connector):
            def fetch(self, source):
                rows = [r for n in self.products for r in _many(n, 1)]
                yield ScrapedTable(source.source_key, PRODUCT_PRICES.kind, "https://x",
                                   make_payload([one_row()]).header, rows)

        result = _crawl(conn, entry, _Thin(["1", "2", "3", "4", "5", "6"]))

        assert canary_breach(entry, result.rows, previous), "the fixture must breach the canary"
        assert "vanished" not in _status(conn).values()
        assert any("volume canary failed" in n and "4 of 10" in n for n in result.ingest.notices), (
            result.ingest.notices)
    finally:
        conn.close()


def test_the_column_shows_where_the_mark_is_all_it_says(tmp_path):
    """GPP_ENERGY and ARAMCO_FUEL_SA are all `unknown`, which hides the column. A row carrying
    the mark must still have a column to read it in."""
    entry = make_entry()
    conn = dbmod.connect(tmp_path / "u.db")
    dbmod.migrate(conn)
    try:
        ingest_payloads(conn, entry, [make_payload(
            [_row(str(n), availability="unknown") for n in range(1, 5)])])

        class _Unknown(_Connector):
            def fetch(self, source):
                yield ScrapedTable(source.source_key, PRODUCT_PRICES.kind, "https://x",
                                   make_payload([one_row()]).header,
                                   [_row(p, availability="unknown") for p in self.products])

        _crawl(conn, entry, _Unknown(["1", "2", "3"]))

        table = reports.table_payload(conn, entry.source_key)
        assert any(r["availability"] == "no_longer_listed" for r in table["rows"])
        assert any(c["key"] == "availability" for c in table["columns"])
    finally:
        conn.close()


def test_the_changes_page_says_what_the_table_says(tmp_path):
    """The real page, drawn by the engine: its summary chip and its row chip both print the
    change type. It is the only surface that does: the panel's own label is computed and
    never drawn."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from scrapex.webui.app import create_app

    path = tmp_path / "w.db"
    entry = make_entry()
    conn = dbmod.connect(path)
    dbmod.migrate(conn)
    ingest_payloads(conn, entry, [make_payload([_row("1"), _row("2")])])
    _crawl(conn, entry, _Connector(["1"]))
    conn.commit()
    conn.close()

    page = TestClient(create_app(path, manifest_path=MANIFEST_FILE)).get(
        "/changes", params={"source_key": entry.source_key}).text

    assert "1 no longer listed" in " ".join(page.split())
    assert "removed" not in page
    assert "vanished" not in page


def test_the_change_feed_says_what_the_table_says(seeded):
    """The same state must not have three names, and "vanished" claims what a crawl cannot know."""
    entry, conn = seeded
    _crawl(conn, entry, _Connector(["1", "2", "3"]))
    gone = next(e for e in changes.recent_changes(conn, entry.source_key)
                if e.get("change_type") == "removed")
    assert (gone["field_label"], gone["display_previous"], gone["display_new"]) == (
        "listing", "Listed", "No longer listed")

    _crawl(conn, entry, _Connector(["1", "2", "3", "4"]))
    back = next(e for e in changes.recent_changes(conn, entry.source_key)
                if e.get("change_type") == "returned")
    assert (back["display_previous"], back["display_new"]) == ("No longer listed", "Listed")


# ---- the edges -----------------------------------------------------------------

class _TwoTables(_Connector):
    def __init__(self, first, second, refused_first=(), refused_second=()):
        super().__init__([])
        self.first, self.second = first, second
        self.refused_first, self.refused_second = list(refused_first), list(refused_second)

    def fetch(self, source):
        header = make_payload([one_row()]).header
        yield ScrapedTable(source.source_key, PRODUCT_PRICES.kind, "https://x#1", header,
                           [_row(p) for p in self.first], refused_products=self.refused_first)
        yield ScrapedTable(source.source_key, PRODUCT_PRICES.kind, "https://x#2", header,
                           [_row(p) for p in self.second], refused_products=self.refused_second)


@pytest.mark.parametrize("connector", [
    _TwoTables(["1", "2", "3"], ["4"]),
    _TwoTables(["4"], ["1", "2", "3"]),
    _TwoTables(["1", "2"], ["3"], refused_first=["4"]),
    _TwoTables(["1", "2"], ["3"], refused_second=["4"]),
], ids=["seen in the second page", "seen in the first page",
        "refused on the first page", "refused on the last page"])
def test_every_page_of_the_crawl_counts(seeded, connector):
    entry, conn = seeded
    _crawl(conn, entry, connector)
    assert set(_status(conn).values()) == {"active"}


def test_zero_rows_after_a_census_claim_marks_nothing(seeded):
    entry, conn = seeded
    _crawl(conn, entry, _Connector([]))
    assert set(_status(conn).values()) == {"active"}
    assert conn.execute("SELECT COUNT(*) FROM change_event WHERE change_type = 'removed'"
                        ).fetchone()[0] == 0


def test_every_product_refused_marks_nothing(seeded):
    entry, conn = seeded
    _crawl(conn, entry, _Connector([], refused=["1", "2", "3", "4"]))
    assert set(_status(conn).values()) == {"active"}


def test_a_clean_crawl_says_nothing(seeded):
    entry, conn = seeded
    result = _crawl(conn, entry, _Connector(["1", "2", "3", "4"]))
    assert not [n for n in result.ingest.notices if "no longer listed" in n], result.ingest.notices


def test_a_second_crawl_still_missing_records_one_removal(seeded):
    entry, conn = seeded
    _crawl(conn, entry, _Connector(["1", "2", "3"]))
    _crawl(conn, entry, _Connector(["1", "2", "3"]))
    assert conn.execute("SELECT COUNT(*) FROM change_event WHERE change_type = 'removed'"
                        ).fetchone()[0] == 1


def test_two_sources_sharing_an_external_id_do_not_cross(tmp_path):
    """DIESEL is one external id on two of his sources today."""
    conn = dbmod.connect(tmp_path / "s.db")
    dbmod.migrate(conn)
    try:
        a = make_entry()
        b = make_entry(source_key="OTHERSHOP", source_name="Other", base_url="https://other.example")
        ingest_payloads(conn, a, [make_payload([_row("1"), _row("2")])])
        ingest_payloads(conn, b, [make_payload([_row("1"), _row("2")], source_key="OTHERSHOP")])

        _crawl(conn, a, _Connector(["1"]))

        got = {(r[0], r[1]): r[2] for r in conn.execute(
            "SELECT ss.source_key, sp.external_product_id, sp.status FROM source_product sp "
            "JOIN source_site ss ON ss.source_id = sp.source_id")}
        assert got == {("ELSEWEDYSHOP", "1"): "active", ("ELSEWEDYSHOP", "2"): "vanished",
                       ("OTHERSHOP", "1"): "active", ("OTHERSHOP", "2"): "active"}
    finally:
        conn.close()


def test_max_drop_pct_zero_marks_nothing_and_says_so(tmp_path):
    """0 is a bound, not the absence of one."""
    conn = dbmod.connect(tmp_path / "z.db")
    dbmod.migrate(conn)
    try:
        entry = make_entry(max_drop_pct=0)
        ingest_payloads(conn, entry, [make_payload([_row("1"), _row("2"), _row("3")])])
        result = _crawl(conn, entry, _Connector(["1", "2"]))
        assert set(_status(conn).values()) == {"active"}
        assert any("not marked" in n for n in result.ingest.notices), result.ingest.notices
    finally:
        conn.close()


def test_a_crawl_with_no_price_rows_marks_nothing(seeded):
    """Details and no prices would pass the canary, whose count is every row, and would
    otherwise read as the whole catalogue missing."""
    entry, conn = seeded
    result = SimpleNamespace(notices=[], run_id=None)

    mark_unlisted_products(conn, entry, [], [], result)

    assert set(_status(conn).values()) == {"active"}
    assert result.notices == []


def test_the_bound_holds_where_the_rows_did_not_fall(tmp_path):
    """Zero is a bound, not the absence of one. The product is gone while the row count holds,
    so the canary passes and only the bound can refuse it."""
    conn = dbmod.connect(tmp_path / "b.db")
    dbmod.migrate(conn)
    try:
        entry = make_entry(max_drop_pct=0)
        ingest_payloads(conn, entry, [make_payload([_row("1"), _row("2"), _row("3")])])

        class _SameCount(_Connector):
            def fetch(self, source):
                rows = [_row("1"), _row("2"),
                        one_row(external_product_id="1", external_variant_id="v1b",
                                external_sku="SKU1b")]
                yield ScrapedTable(source.source_key, PRODUCT_PRICES.kind, "https://x",
                                   make_payload([one_row()]).header, rows)

        result = _crawl(conn, entry, _SameCount([]))

        assert set(_status(conn).values()) == {"active"}
        assert any("over the 0%" in n for n in result.ingest.notices), result.ingest.notices
    finally:
        conn.close()


def test_a_partial_run_with_a_new_observation_marks_nothing(seeded):
    """With no new observation a defect reads FAILED, so PARTIAL needs a price that moved."""
    entry, conn = seeded

    class _Moved(_Connector):
        def fetch(self, source):
            rows = [_row("1", price="1,300.00", price_before="1,300.00"), _row("2")]
            yield ScrapedTable(source.source_key, PRODUCT_PRICES.kind, "https://x",
                               make_payload([one_row()]).header, rows,
                               defects=["the English store failed"])

    result = _crawl(conn, entry, _Moved([]))
    assert result.ingest.status.value == "partial", result.ingest.status
    assert _status(conn)["3"] == "active"


def test_a_row_error_in_the_run_marks_nothing(seeded):
    entry, conn = seeded

    class _Bad(_Connector):
        def fetch(self, source):
            rows = [_row("1", price="not a number", price_before="", price_sale="")]
            yield ScrapedTable(source.source_key, PRODUCT_PRICES.kind, "https://x",
                               make_payload([one_row()]).header, rows)

    result = _crawl(conn, entry, _Bad([]))
    assert result.ingest.status.value != "success", "the row must error"
    assert set(_status(conn).values()) == {"active"}


def test_a_proven_crawl_after_a_rebuild_leaves_what_it_did_not_find_marked(seeded):
    entry, conn = seeded
    _crawl(conn, entry, _Connector(["1", "2", "3"]), archive_first=True)
    assert _status(conn) == {"1": "active", "2": "active", "3": "active", "4": "vanished"}


# ---- end to end, on the two manifest entries that can prove a census -------------

def _manifest(key):
    """The real entry, with its expected volume off: these fixtures hold four products."""
    return load_manifest(MANIFEST_FILE).get(key).model_copy(update={"min_expected_rows": None})


@pytest.fixture()
def warehouse(tmp_path, monkeypatch):
    monkeypatch.setattr(localinbox, "JOURNAL_DIR", tmp_path / "journal")
    path = tmp_path / "w.db"
    conn = dbmod.connect(path)
    dbmod.migrate(conn)
    yield path, conn
    conn.close()


def _real(fetcher, connector_cls, conn, entry, **kwargs):
    connector = connector_cls(fetcher)
    fetcher.requests_count = getattr(fetcher, "requests_count", 0)
    original = capmod.build_connector
    capmod.build_connector = lambda e, rules, crawl=None: (connector, fetcher)
    try:
        result = capture_source(conn, entry, **kwargs)
    finally:
        capmod.build_connector = original
    conn.commit()
    return result, connector


def _fresh(path, sql, *args):
    """Read through another connection, so what was asserted is what was committed."""
    other = sqlite3.connect(path)
    try:
        return other.execute(sql, args).fetchall()
    finally:
        other.close()


def _sheet(conn, key):
    _name, header, rows = workbook_tables(conn, key)[0]
    return {row[header.index("sku")]: row[header.index("availability")] for row in rows}


def _table(conn, key):
    return {r["sku"]: r["availability"] for r in reports.table_payload(conn, key)["rows"]}


def test_madar_is_marked_and_returns_end_to_end(warehouse):
    path, conn = warehouse
    entry = _manifest("MADAR")
    every = [[_simple("A"), _simple("B")], [_simple("C"), _simple("D")]]
    result, connector = _real(_MagentoFetcher(every), MagentoGraphqlConnector, conn, entry)
    assert result.ingest.status.value == "success", result.ingest.errors
    assert connector.census_proven is True

    _real(_MagentoFetcher([[_simple("A"), _simple("B")], [_simple("C")]]),
          MagentoGraphqlConnector, conn, entry)
    assert _fresh(path, "SELECT external_product_id FROM source_product "
                        "WHERE status = 'vanished'") == [("D",)]
    assert _table(conn, "MADAR")["SKU-D"] == "no_longer_listed"
    assert _sheet(conn, "MADAR")["SKU-D"] == "no_longer_listed"
    assert _table(conn, "MADAR")["SKU-A"] == "in_stock"

    _real(_MagentoFetcher(every), MagentoGraphqlConnector, conn, entry)
    assert _fresh(path, "SELECT status FROM source_product WHERE external_product_id = 'D'"
                  ) == [("active",)]
    assert _table(conn, "MADAR")["SKU-D"] == "in_stock"
    assert _sheet(conn, "MADAR")["SKU-D"] == "in_stock"


def test_madar_names_a_refusal_by_its_uid_on_every_page(warehouse):
    """MADAR's ids are uids. Named by SKU, every refused product would read as gone."""
    _path, conn = warehouse
    entry = _manifest("MADAR")
    _real(_MagentoFetcher([[_simple("A"), _simple("B")], [_simple("C"), _simple("D")]]),
          MagentoGraphqlConnector, conn, entry)

    _real(_MagentoFetcher([[_simple("A"), _ranged("B")], [_simple("C"), _ranged("D")]]),
          MagentoGraphqlConnector, conn, entry)

    assert set(_status(conn).values()) == {"active"}


def test_sika_is_marked_and_returns_end_to_end(warehouse):
    path, conn = warehouse
    entry = _manifest("SIKAEGSHOP")

    class _Details(_JsonFetcher):
        def get(self, url, **kwargs):
            last = url.rstrip("/").split("/")[-1]
            if last.isdigit():
                return _JsonResponse(_sika(int(last)))
            return super().get(url, **kwargs)

    every = [[_sika(1), _sika(2)], [_sika(3), _sika(4)]]
    result, connector = _real(_Details(every, total=4), CustomJsonConnector, conn, entry)
    assert result.ingest.status.value == "success", result.ingest.errors
    assert connector.census_proven is True

    _real(_Details([[_sika(1), _sika(2)], [_sika(3)]], total=3), CustomJsonConnector, conn, entry)
    assert _fresh(path, "SELECT external_product_id FROM source_product "
                        "WHERE status = 'vanished'") == [("4",)]
    assert sum(v == "no_longer_listed" for v in _sheet(conn, "SIKAEGSHOP").values()) == 1

    _real(_Details(every, total=4), CustomJsonConnector, conn, entry)
    assert "no_longer_listed" not in _sheet(conn, "SIKAEGSHOP").values()


def test_a_madar_run_refused_at_store_config_marks_nothing(warehouse):
    """#1848 stops the run at its first request."""
    path, conn = warehouse
    entry = _manifest("MADAR")
    _real(_MagentoFetcher([[_simple("A"), _simple("B")]]), MagentoGraphqlConnector, conn, entry)

    class _Blank(_MagentoFetcher):
        def post(self, url, json=None, **kwargs):
            if "storeConfig" in (json or {}).get("query", ""):
                return _MagentoResponse({"data": {"storeConfig": {"weight_unit": ""}}})
            return super().post(url, json=json, **kwargs)

    with pytest.raises(GraphqlRefused):
        _real(_Blank([[_simple("A")]]), MagentoGraphqlConnector, conn, entry)

    assert set(_status(conn).values()) == {"active"}
    assert _fresh(path, "SELECT COUNT(*) FROM change_event WHERE change_type = 'removed'") == [(0,)]


def test_a_madar_run_whose_english_store_failed_marks_nothing(warehouse):
    _path, conn = warehouse
    entry = _manifest("MADAR")
    _real(_MagentoFetcher([[_simple("A"), _simple("B")]]), MagentoGraphqlConnector, conn, entry)

    class _NoEnglish(_MagentoFetcher):
        def post(self, url, json=None, **kwargs):
            if (kwargs.get("headers") or {}).get("Store"):
                raise ConnectionError("english store down")
            return super().post(url, json=json, **kwargs)

    result, connector = _real(_NoEnglish([[_simple("A")]]), MagentoGraphqlConnector, conn, entry)

    assert connector.census_proven is True
    assert result.ingest.status.value != "success"
    assert set(_status(conn).values()) == {"active"}


def test_the_job_path_carries_the_run_and_the_job(warehouse):
    """The path the engine takes: the journal, then the mark."""
    path, conn = warehouse
    entry = make_entry()
    ingest_payloads(conn, entry, [make_payload([_row("1"), _row("2")])])
    conn.commit()
    ref = create_job(conn, [entry.source_key])
    job_id = get_job(conn, ref)["job_id"] if isinstance(ref, str) else ref

    _crawl(conn, entry, _Connector(["1"]), job_id=job_id)
    conn.commit()

    assert _fresh(path, "SELECT job_id = ?, run_id IS NOT NULL FROM change_event "
                        "WHERE change_type = 'removed'", job_id) == [(1, 1)]


def test_a_journal_page_that_will_not_read_back_marks_nothing(warehouse, monkeypatch):
    _path, conn = warehouse
    entry = make_entry()
    ingest_payloads(conn, entry, [make_payload([_row("1"), _row("2")])])
    conn.commit()
    ref = create_job(conn, [entry.source_key])
    job_id = get_job(conn, ref)["job_id"] if isinstance(ref, str) else ref
    real = localinbox.read_payloads

    def lossy(base, key):
        read = real(base, key)
        return SimpleNamespace(payloads=read.payloads,
                               report=lambda: ["page-2: did not read back"])

    monkeypatch.setattr(localinbox, "read_payloads", lossy)
    result = _crawl(conn, entry, _Connector(["1"]), job_id=job_id)

    assert result.ingest.status.value != "success"
    assert set(_status(conn).values()) == {"active"}


# ---- holes a proof must not have ----------------------------------------------

def test_a_store_that_states_no_page_count_proves_nothing():
    """It has not said page 1 was its last."""

    class _NoCount(_MagentoFetcher):
        def post(self, url, json=None, **kwargs):
            answer = super().post(url, json=json, **kwargs)
            products = (answer.json().get("data") or {}).get("products")
            if products is not None and products.get("items"):
                del products["page_info"]
            return answer

    connector = MagentoGraphqlConnector(_NoCount([[_simple("A")], [_simple("B")]]))
    list(connector.fetch(_magento_entry()))
    assert connector.census_proven is False


def test_a_repeat_across_a_page_edge_is_not_the_stated_total(warehouse):
    """Four items came back and four were stated, but product 2 twice and product 4 never."""
    _path, conn = warehouse
    entry = _sika_entry()
    _real(_JsonFetcher([[_sika(1), _sika(2)], [_sika(3), _sika(4)]], total=4),
          CustomJsonConnector, conn, entry)

    _result, connector = _real(_JsonFetcher([[_sika(1), _sika(2)], [_sika(2), _sika(3)]], total=4),
                               CustomJsonConnector, conn, entry)

    assert connector.census_proven is False
    assert _status(conn)["4"] == "active", "marked on a walk that never met it"


def test_an_api_that_states_no_total_proves_nothing():
    class _NoTotal(_JsonFetcher):
        def get(self, url, **kwargs):
            answer = super().get(url, **kwargs)
            del answer.json()["pagination"]["total"]
            return answer

    connector = CustomJsonConnector(_NoTotal([[_sika(1)], [_sika(2)]], total=2))
    list(connector.fetch(_sika_entry()))
    assert connector.census_proven is False
