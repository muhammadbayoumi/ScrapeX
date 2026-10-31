"""A product a complete crawl no longer finds is marked, and only then (#1841).

His ruling of 2026-10-31, option (أ): it stays in the table, marked and filterable;
it leaves the file mbiX reads; its history stays; and it comes back by itself.

WHY THE MARK SAYS "NO LONGER LISTED" AND NOT "GONE FROM THE SITE". Of three unseen
madar products opened on 2026-10-31, one answered 404 and two redirected to a new
parent product that holds them as options. The crawl knows the record is not in the
listing. It cannot know why, and a state must not claim a cause it cannot know.

THE GATE IS THE POINT, as in sightings.mark_departures: a connector that did not
prove it walked the whole listing marks nothing, and a product it met and refused
is not gone. Masdar's last run said "905 product(s) publish no price at all".
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scrapex import capture as capmod
from scrapex import db as dbmod
from scrapex import reports
from scrapex.capture import capture_source
from scrapex.connectors.base import ScrapedTable
from scrapex.connectors.custom_json import CustomJsonConnector
from scrapex.connectors.magento import MagentoGraphqlConnector
from scrapex.ingest import ingest_payloads
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


def test_the_export_leaves_it_out(seeded):
    """A price that no longer exists must not be read by mbiX as a current one."""
    entry, conn = seeded
    _crawl(conn, entry, _Connector(["1", "2", "3"]))

    header, rows = reports.export_source_table(conn, entry.source_key)[:2]

    skus = [row[header.index("sku")] for row in rows]
    assert sorted(skus) == ["SKU1", "SKU2", "SKU3"]


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
    return {"__typename": "SimpleProduct", "uid": uid, "sku": uid, "url_key": uid,
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


def test_the_web_page_offers_the_state_as_a_filter():
    from scrapex.webui.app import AVAILABILITY_OPTIONS
    assert "no_longer_listed" in AVAILABILITY_OPTIONS
